from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.core.doctype.file.file import File as FrappeFile

from core.s3_file_storage import (
	file_uses_s3,
	s3_enabled,
	s3_get_bytes,
	s3_head_exists,
)

if TYPE_CHECKING:
	pass


class File(FrappeFile):
	def validate_file_path(self):
		if s3_enabled() and file_uses_s3(self):
			return
		super().validate_file_path()

	def validate_file_on_disk(self):
		if s3_enabled() and file_uses_s3(self):
			if not s3_head_exists(self):
				frappe.throw(_("File {0} does not exist").format(self.file_url), IOError)
			return
		super().validate_file_on_disk()

	def exists_on_disk(self):
		if s3_enabled() and file_uses_s3(self):
			return s3_head_exists(self)
		return super().exists_on_disk()

	def get_content(self) -> bytes:
		if self.is_folder:
			return super().get_content()

		if self.get("content"):
			return super().get_content()

		if s3_enabled() and file_uses_s3(self):
			if self.file_url:
				self.validate_file_url()
			raw = s3_get_bytes(self)
			self._content = raw
			try:
				self._content = self._content.decode()
			except UnicodeDecodeError:
				pass
			return self._content

		return super().get_content()
