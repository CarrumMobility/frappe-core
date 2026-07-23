# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


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
	pass
