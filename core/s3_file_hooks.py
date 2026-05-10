from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import frappe

from core.s3_file_storage import (
	build_object_key,
	file_uses_s3,
	public_file_url,
	s3_delete,
	s3_enabled,
	s3_put_bytes,
)

if TYPE_CHECKING:
	from frappe.core.doctype.file.file import File


def _unique_safe_file_name(file_doc: File) -> str:
	"""
	Frappe's generate_file_name() checks the local disk; with S3-only writes that path is
	often missing, so the same display name would reuse one S3 key and overwrite objects.
	Always embed content hash (or a random id) in the stored file name.
	"""
	raw = re.sub(r"[/\\%?#]", "_", file_doc.file_name or "file")
	stem, ext = os.path.splitext(raw)
	if not stem:
		stem = "file"
	uid = (file_doc.content_hash or "").strip() or frappe.generate_hash(length=16)
	# Short prefix keeps keys readable; full md5 would also work
	short = uid[-12:] if len(uid) >= 12 else uid
	return f"{stem}_{short}{ext}"


def write_file(file_doc: File) -> dict:
	if not s3_enabled():
		return file_doc.save_file_on_filesystem()

	safe = _unique_safe_file_name(file_doc)
	file_doc.file_name = safe
	site = getattr(frappe.local, "site", "") or "site"
	object_key = build_object_key(site, bool(file_doc.is_private), safe)

	data = file_doc._content
	if isinstance(data, str):
		data = data.encode("utf-8")

	s3_put_bytes(object_key, data, file_doc.file_name)
	file_doc.file_url = public_file_url(object_key)
	return {"file_name": safe, "file_url": file_doc.file_url}


def delete_file_data_content(file_doc: File, only_thumbnail: bool = False) -> None:
	if not s3_enabled():
		file_doc.delete_file_from_filesystem(only_thumbnail=only_thumbnail)
		return
	if only_thumbnail:
		file_doc.delete_file_from_filesystem(only_thumbnail=True)
		return
	if file_uses_s3(file_doc):
		s3_delete(file_doc)
	file_doc.delete_file_from_filesystem(only_thumbnail=False)
