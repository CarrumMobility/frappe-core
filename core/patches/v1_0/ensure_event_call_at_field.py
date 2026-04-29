"""Sites that ran an older add_event_callback_fields never got the call_at Custom Field.

Creates Event.call_at (Datetime) if missing so tabEvent gets the column on migrate.
"""

import frappe


def execute():
	if frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": "call_at"}):
		return

	insert_after = (
		"reference_call_session"
		if frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": "reference_call_session"})
		else "location"
	)

	doc = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Event",
			"module": "Platform",
			"fieldname": "call_at",
			"fieldtype": "Datetime",
			"label": "Call at",
			"insert_after": insert_after,
			"in_list_view": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Event")
