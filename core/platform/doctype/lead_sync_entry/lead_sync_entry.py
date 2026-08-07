# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cstr


def find_lead_sync_entry_name_by_vendor_id(
	vendor_id: str | None,
	*,
	prefer_linked: bool = False,
) -> str | None:
	"""Return one Lead Sync Entry name for a vendor id (application-level dedup helper)."""
	vendor_id = cstr(vendor_id).strip()
	if not vendor_id:
		return None

	rows = frappe.get_all(
		"Lead Sync Entry",
		filters={"vendor_id": vendor_id},
		fields=["name", "lead_id"],
		order_by="creation asc",
		limit_page_length=0,
	)
	if not rows:
		return None

	if prefer_linked:
		for row in rows:
			if row.get("lead_id"):
				return row.name

	return rows[0].name


class LeadSyncEntry(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		lead_id: DF.Link | None
		lead_sync_source: DF.Link | None
		raw: DF.JSON | None
		submitted_at: DF.Datetime | None
		vendor_id: DF.Data | None
		vendor_name: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.validate_unique_vendor_id()

	def validate_unique_vendor_id(self):
		vendor_id = cstr(self.vendor_id).strip()
		if not vendor_id:
			return

		existing = find_lead_sync_entry_name_by_vendor_id(vendor_id)
		if existing and existing != self.name:
			frappe.throw(
				frappe._("A Lead Sync Entry already exists for Vendor Id {0}").format(vendor_id),
				frappe.DuplicateEntryError,
			)
