"""Event CRM callbacks: extend Event Category + Custom Fields (replaces edits on Frappe Event DocType)."""

import frappe


def execute():
	_ensure_event_category_callback_option()
	_ensure_custom_field(
		"reference_call_session",
		{
			"fieldtype": "Link",
			"label": "Reference Call Session",
			"options": "Call Session",
			"insert_after": "location",
			"in_list_view": 1,
		},
	)
	_ensure_custom_field(
		"call_at",
		{
			"fieldtype": "Datetime",
			"label": "Call at",
			"insert_after": "reference_call_session",
			"in_list_view": 1,
		},
	)
	_ensure_custom_field(
		"callback_status",
		{
			"fieldtype": "Select",
			"label": "Callback status",
			"options": "Scheduled\nTriggered\nMissed\nCompleted\nOverride\nDone",
			"insert_after": "call_at",
			"in_list_view": 1,
		},
	)
	frappe.clear_cache(doctype="Event")


def _ensure_event_category_callback_option():
	if frappe.db.exists(
		"Property Setter",
		{"doc_type": "Event", "field_name": "event_category", "property": "options"},
	):
		return

	frappe.make_property_setter(
		{
			"doctype": "Event",
			"fieldname": "event_category",
			"property": "options",
			"value": "Event\nMeeting\nCall\nSent/Received Email\nOther\nCallback\nVisit Date",
		},
		module="Platform",
	)


def _ensure_custom_field(fieldname: str, field: dict):
	if frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": fieldname}):
		return

	doc = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Event",
			"module": "Platform",
			"fieldname": fieldname,
			**field,
		}
	)
	doc.insert(ignore_permissions=True)
