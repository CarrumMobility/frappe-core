"""Rename Agent Performance unique_date_confirmed -> unique_schedules_walkin."""

import frappe


def execute():
	if not frappe.db.table_exists("Agent Performance"):
		return

	if frappe.db.has_column("Agent Performance", "unique_date_confirmed") and not frappe.db.has_column(
		"Agent Performance", "unique_schedules_walkin"
	):
		frappe.db.rename_column(
			"tabAgent Performance",
			"unique_date_confirmed",
			"unique_schedules_walkin",
		)

	for name in frappe.get_all(
		"DocField",
		filters={"parent": "Agent Performance", "fieldname": "unique_date_confirmed"},
		pluck="name",
	):
		frappe.db.set_value(
			"DocField",
			name,
			{"fieldname": "unique_schedules_walkin", "label": "Unique schedules walkin"},
			update_modified=False,
		)

	frappe.clear_cache(doctype="Agent Performance")
