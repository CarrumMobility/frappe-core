from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

import frappe
from frappe import _


class FileStorageType(StrEnum):
	DEFAULT = "DEFAULT"
	S3 = "S3"


def get_file_storage_type(conf: Any | None = None) -> FileStorageType:
	"""Return the configured file storage type, defaulting only when it is absent."""
	config = conf if conf is not None else frappe.conf
	raw_value = config.get("file_storage_type")
	if raw_value is None or raw_value == "":
		return FileStorageType.DEFAULT

	if str(raw_value).strip() == "GCS":
		frappe.throw(
			_(
				"file_storage_type GCS is no longer supported. "
				"Use file_storage_type S3 with s3_endpoint_url set to https://storage.googleapis.com, "
				"HMAC credentials in aws_access_key_id/aws_secret_access_key, and s3_bucket/s3_bucket_prefix."
			),
			frappe.ValidationError,
		)

	try:
		return FileStorageType(raw_value)
	except (TypeError, ValueError):
		accepted = ", ".join(storage_type.value for storage_type in FileStorageType)
		frappe.throw(
			_("Unsupported file_storage_type {0}. Expected one of: {1}").format(
				frappe.bold(str(raw_value)),
				accepted,
			),
			frappe.ValidationError,
		)


def ensure_site_files_dirs() -> None:
	"""Create the site's local files folders before an upload is handled.

	Frappe 16 stages every upload (chunked or not) in `<site>/{private,public}/files/.temp-*`
	before handing it to the storage backend, even with S3 storage. Sites provisioned by hand,
	rather than by `bench new-site`, do not have these folders and upload_file fails with a 500.
	"""
	request = getattr(frappe.local, "request", None)
	if not request or not request.path.endswith("/upload_file"):
		return
	for scope in ("private", "public"):
		os.makedirs(frappe.get_site_path(scope, "files"), exist_ok=True)
