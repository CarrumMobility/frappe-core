# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class payment_logs(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		image: DF.Text | None
		lead: DF.Link | None
		raw: DF.JSON
		sd_breakup_amount: DF.Currency
		settlement_breakup_amount: DF.Currency
		status: DF.Literal["Captured", "Failed",'Transferred', 'Rejected']
		transaction_date: DF.Datetime
		utr: DF.Data | None
	# end: auto-generated types
	pass
