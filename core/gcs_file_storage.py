from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING
from urllib.parse import unquote

import frappe
from frappe import _
from google.api_core.exceptions import NotFound
from google.cloud import storage

from core.file_storage import FileStorageType, get_file_storage_type

if TYPE_CHECKING:
	from frappe.core.doctype.file.file import File


def gcs_enabled() -> bool:
	if get_file_storage_type() != FileStorageType.GCS:
		return False
	require_gcs_config()
	return True


def require_gcs_config() -> None:
	if get_file_storage_type() != FileStorageType.GCS:
		frappe.throw(_("GCS file storage is not selected"), frappe.ValidationError)
	if not (frappe.conf.get("gcs_bucket") or "").strip():
		frappe.throw(
			_("gcs_bucket is required when file_storage_type is GCS"),
			frappe.ValidationError,
		)


def gcs_bucket_prefix() -> str:
	"""Optional public base URL; no trailing slash."""
	return (frappe.conf.get("gcs_bucket_prefix") or "").strip().rstrip("/")


def build_object_key(site: str, is_private: bool, safe_file_name: str) -> str:
	site = site or "site"
	if is_private:
		return f"{site}/private/files/{safe_file_name}"
	return f"{site}/files/{safe_file_name}"


def file_url(object_key: str, is_private: bool) -> str:
	key = object_key.lstrip("/")
	if is_private:
		site = getattr(frappe.local, "site", "") or "site"
		site_prefix = f"{site}/"
		return f"/{key[len(site_prefix):]}" if key.startswith(site_prefix) else f"/{key}"

	base = gcs_bucket_prefix()
	if base:
		return f"{base}/{key}"
	bucket = (frappe.conf.get("gcs_bucket") or "").strip()
	return f"https://storage.googleapis.com/{bucket}/{key}"


def gcs_object_key(file_doc: File) -> str | None:
	url = unquote((file_doc.file_url or "").strip())
	prefix = gcs_bucket_prefix()
	if prefix and url.startswith(f"{prefix}/"):
		return url[len(prefix) :].lstrip("/") or None

	bucket = (frappe.conf.get("gcs_bucket") or "").strip()
	google_prefix = f"https://storage.googleapis.com/{bucket}/"
	if bucket and url.startswith(google_prefix):
		return url[len(google_prefix) :].lstrip("/") or None

	if url.startswith("/private/files/") or url.startswith("/files/"):
		site = getattr(frappe.local, "site", "") or "site"
		return f"{site}/{url.lstrip('/')}"
	if url.startswith(("http://", "https://")):
		return None
	return None


def file_uses_gcs(file_doc: File) -> bool:
	if not gcs_enabled():
		return False
	return gcs_object_key(file_doc) is not None


def gcs_client() -> storage.Client:
	"""Use Google Application Default Credentials from the runtime environment."""
	require_gcs_config()
	try:
		return storage.Client()
	except Exception as exc:
		frappe.throw(
			_("Unable to initialize GCS with Application Default Credentials: {0}").format(str(exc)),
			frappe.ValidationError,
		)


def _bucket():
	return gcs_client().bucket(frappe.conf.gcs_bucket)


def gcs_put_bytes(object_key: str, content: bytes, file_name: str | None) -> None:
	content_type = mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"
	_bucket().blob(object_key).upload_from_string(content, content_type=content_type)


def gcs_head_exists(file_doc: File) -> bool:
	key = gcs_object_key(file_doc)
	if not key:
		return False
	return _bucket().blob(key).exists()


def gcs_get_bytes(file_doc: File) -> bytes:
	key = gcs_object_key(file_doc)
	if not key:
		frappe.throw(_("Cannot resolve GCS object key for this file"))
	return _bucket().blob(key).download_as_bytes()


def gcs_delete(file_doc: File) -> None:
	key = gcs_object_key(file_doc)
	if not key:
		return
	try:
		_bucket().blob(key).delete()
	except NotFound:
		pass
	except Exception:
		frappe.log_error(frappe.get_traceback(), "GCS delete failed")
