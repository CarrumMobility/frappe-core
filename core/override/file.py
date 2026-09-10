from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.core.doctype.file.file import File as FrappeFile

from core.file_storage import FileStorageType, get_file_storage_type
from core.gcs_file_storage import (
	file_uses_gcs,
	gcs_get_bytes,
	gcs_head_exists,
)
from core.s3_file_storage import (
	file_uses_s3,
	s3_enabled,
	s3_get_bytes,
	s3_head_exists,
)

if TYPE_CHECKING:
	pass


class File(FrappeFile):
	def _selected_cloud_backend(self):
		storage_type = get_file_storage_type()
		if storage_type == FileStorageType.S3 and s3_enabled() and file_uses_s3(self):
			return "S3"
		if storage_type == FileStorageType.GCS and file_uses_gcs(self):
			return "GCS"
		return None

	def validate_file_path(self):
		if self._selected_cloud_backend():
			return
		super().validate_file_path()

	def validate_file_on_disk(self):
		backend = self._selected_cloud_backend()
		if backend:
			exists = s3_head_exists(self) if backend == "S3" else gcs_head_exists(self)
			if not exists:
				frappe.throw(_("File {0} does not exist").format(self.file_url), IOError)
			return
		super().validate_file_on_disk()

	def exists_on_disk(self):
		backend = self._selected_cloud_backend()
		if backend == "S3":
			return s3_head_exists(self)
		if backend == "GCS":
			return gcs_head_exists(self)
		return super().exists_on_disk()

	def get_content(self) -> bytes:
		if self.is_folder:
			return super().get_content()

		if self.get("content"):
			return super().get_content()

		backend = self._selected_cloud_backend()
		if backend:
			if self.file_url:
				self.validate_file_url()
			raw = s3_get_bytes(self) if backend == "S3" else gcs_get_bytes(self)
			self._content = raw
			try:
				self._content = self._content.decode()
			except UnicodeDecodeError:
				pass
			return self._content

		return super().get_content()
