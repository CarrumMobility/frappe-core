# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Userdialersessionlogs(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active_at: DF.Datetime | None
		campaign_id: DF.Data
		campaign_name: DF.Data
		inactive_at: DF.Datetime | None
		status: DF.Literal["ACTIVE", "INACTIVE"]
		user: DF.Link
		inactive_reason: DF.Data | None
	# end: auto-generated types
	pass
