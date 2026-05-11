# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Apihitlog(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		api_name: DF.Data | None
		created_by: DF.Link | None
		end_point: DF.Data | None
		error_message: DF.Data | None
		execution_time: DF.Float
		request_payload: DF.JSON | None
		response: DF.JSON | None
		status_code: DF.Int
	# end: auto-generated types
	pass
