"""Rename Call Session field phone_number -> lead_phone (column + DocField) before model sync."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	if frappe.db.has_column("Call Session", "phone_number") and not frappe.db.has_column(
		"Call Session", "lead_phone"
	):
		frappe.db.rename_column("Call Session", "phone_number", "lead_phone")

	for name in frappe.get_all(
		"DocField",
		filters={"parent": "Call Session", "fieldname": "phone_number"},
		pluck="name",
	):
		frappe.db.set_value(
			"DocField",
			name,
			{"fieldname": "lead_phone", "label": "Lead phone"},
			update_modified=False,
		)

	frappe.clear_cache(doctype="Call Session")
