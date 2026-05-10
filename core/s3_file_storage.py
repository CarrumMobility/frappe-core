from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING
from urllib.parse import unquote

import boto3
import frappe
from botocore.exceptions import ClientError

if TYPE_CHECKING:
	from frappe.core.doctype.file.file import File


def s3_enabled() -> bool:
	c = frappe.conf
	return bool(c.get("s3_file_storage_enabled")) and bool(c.get("s3_bucket"))


def s3_bucket_prefix() -> str:
	"""Public base URL for stored file_url; no trailing slash."""
	return (frappe.conf.get("s3_bucket_prefix") or "").strip().rstrip("/")


def public_file_url(object_key: str) -> str:
	"""
	Stored File.file_url: prefix + S3 object key when s3_bucket_prefix is set.
	Without prefix: Frappe-style path /private/files/... or /files/... (site segment stripped from key).
	"""
	base = s3_bucket_prefix()
	key = object_key.lstrip("/")
	if base:
		return f"{base}/{key}"
	site = getattr(frappe.local, "site", "") or "site"
	prefix_site = f"{site}/"
	if key.startswith(prefix_site):
		return f"/{key[len(prefix_site) :]}"
	return f"/{key}"


def build_object_key(site: str, is_private: bool, safe_file_name: str) -> str:
	"""S3 object key: {site}/private/files/{name} or {site}/files/{name}."""
	site = site or "site"
	if is_private:
		return f"{site}/private/files/{safe_file_name}"
	return f"{site}/files/{safe_file_name}"


def s3_object_key(file_doc: File) -> str | None:
	"""
	Resolve S3 key from File.file_url: prefixed URL, or legacy /private/files & /files.
	Returns None if this file is not stored in our S3 layout.
	"""
	url = unquote((file_doc.file_url or "").strip())
	prefix = s3_bucket_prefix()
	if prefix and url.startswith(prefix):
		return url[len(prefix) :].lstrip("/") or None
	if url.startswith("/private/files/") or url.startswith("/files/"):
		site = getattr(frappe.local, "site", "") or "site"
		path = url.lstrip("/")
		return f"{site}/{path}"
	if url.startswith(("http://", "https://")):
		return None
	return None


def file_uses_s3(file_doc: File) -> bool:
	if not s3_enabled():
		return False
	url = (file_doc.file_url or "").strip()
	prefix = s3_bucket_prefix()
	if prefix and url.startswith(prefix):
		return True
	if url.startswith("/private/files/") or url.startswith("/files/"):
		return True
	return False


def is_s3_logical_url(file_doc: File) -> bool:
	"""Backward-compatible name: true when file is served from our S3 backend."""
	return file_uses_s3(file_doc)


def s3_client():
	c = frappe.conf
	return boto3.client(
		"s3",
		region_name=c.get("s3_region") or "us-east-1",
		aws_access_key_id=c.get("aws_access_key_id") or c.get("s3_key"),
		aws_secret_access_key=c.get("aws_secret_access_key") or c.get("s3_secret"),
		endpoint_url=c.get("s3_endpoint_url") or None,
	)


def s3_put_bytes(object_key: str, content: bytes, file_name: str | None) -> None:
	bucket = frappe.conf.s3_bucket
	ct = mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"
	s3_client().put_object(Bucket=bucket, Key=object_key, Body=content, ContentType=ct)


def s3_put(file_doc: File, content: bytes) -> None:
	key = s3_object_key(file_doc)
	if not key:
		frappe.throw(frappe._("Cannot resolve S3 object key for this file"))
	s3_put_bytes(key, content, file_doc.file_name)


def s3_head_exists(file_doc: File) -> bool:
	key = s3_object_key(file_doc)
	if not key:
		return False
	try:
		s3_client().head_object(Bucket=frappe.conf.s3_bucket, Key=key)
		return True
	except ClientError:
		return False


def s3_get_bytes(file_doc: File) -> bytes:
	key = s3_object_key(file_doc)
	if not key:
		frappe.throw(frappe._("Cannot resolve S3 object key for this file"))
	obj = s3_client().get_object(Bucket=frappe.conf.s3_bucket, Key=key)
	return obj["Body"].read()


def s3_delete(file_doc: File) -> None:
	key = s3_object_key(file_doc)
	if not key:
		return
	try:
		s3_client().delete_object(Bucket=frappe.conf.s3_bucket, Key=key)
	except ClientError:
		frappe.log_error(frappe.get_traceback(), "S3 delete_object failed")
