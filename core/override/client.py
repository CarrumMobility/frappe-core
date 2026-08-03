# Copyright (c) 2026, core and contributors
# Retry wrapper for frappe.client.set_value on concurrent modification conflicts.

from __future__ import annotations

import frappe
from frappe.client import set_value as _original_set_value
from frappe.utils import cint

DEFAULT_MAX_RETRY_COUNT = 1
MAX_ALLOWED_RETRY_COUNT = 5

log = frappe.logger(__name__)


@frappe.whitelist(methods=["POST", "PUT"])
def set_value(
	doctype: str,
	name: str,
	fieldname: str | dict,
	value=None,
	max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
) -> dict:
	"""Set document field values, retrying only on TimestampMismatchError."""
	retries = min(
		MAX_ALLOWED_RETRY_COUNT,
		max(1, cint(max_retry_count) or DEFAULT_MAX_RETRY_COUNT),
	)

	for attempt in range(retries):
		try:
			return _original_set_value(doctype, name, fieldname, value)
		except frappe.TimestampMismatchError:
			frappe.db.rollback()
			if attempt == retries - 1:
				raise
			log.debug(
				"set_value retry %s/%s for %s/%s",
				attempt + 2,
				retries,
				doctype,
				name,
			)

	raise frappe.TimestampMismatchError
