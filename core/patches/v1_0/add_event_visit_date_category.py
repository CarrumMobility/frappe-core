"""Append Visit Date to Event.event_category options (Property Setter)."""

import frappe


def execute():
	row = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Event", "field_name": "event_category", "property": "options"},
		["name", "value"],
		as_dict=True,
	)
	if not row:
		return
	opts = [x.strip() for x in (row.value or "").split("\n") if x.strip()]
	if "Visit Date" in opts:
		return
	new_val = (row.value or "").rstrip() + "\nVisit Date"
	frappe.db.set_value("Property Setter", row.name, "value", new_val)
	frappe.clear_cache(doctype="Event")
