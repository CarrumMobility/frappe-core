# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Userdialersessionbreaklogs(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		break_code: DF.Data | None
		end_time: DF.Datetime | None
		start_time: DF.Datetime | None
		user: DF.Link | None
		user_dialer_session_log: DF.Link | None
	# end: auto-generated types
	pass
