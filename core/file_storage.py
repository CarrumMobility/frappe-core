from __future__ import annotations

from enum import StrEnum
from typing import Any

import frappe
from frappe import _


class FileStorageType(StrEnum):
	DEFAULT = "DEFAULT"
	S3 = "S3"
	GCS = "GCS"


def get_file_storage_type(conf: Any | None = None) -> FileStorageType:
	"""Return the configured file storage type, defaulting only when it is absent."""
	config = conf if conf is not None else frappe.conf
	raw_value = config.get("file_storage_type")
	if raw_value is None or raw_value == "":
		return FileStorageType.DEFAULT

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
