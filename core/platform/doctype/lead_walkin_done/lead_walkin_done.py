# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Leadwalkindone(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		callback_at: DF.Datetime | None
		created_by: DF.Link | None
		lead: DF.Link | None
		lead_status_link: DF.Link | None
		primary_status: DF.Data | None
		remarks: DF.SmallText | None
		secondary_status: DF.Data | None
		source: DF.Data | None
		telecaller: DF.Link | None
		walkin_form_filled_at: DF.Datetime | None
		business_type: DF.Data | None
		referrer_user_link: DF.Link | None
		referrer_name: DF.Data | None
		referrer_mobile_no: DF.Data | None
		
	# end: auto-generated types

	def before_save(self):
		if not self.walkin_form_filled_at:
			self.walkin_form_filled_at = self.creation