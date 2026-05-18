"""Rename Agent Performance unique_date_confirmed -> unique_schedules_walkin."""

import frappe


def execute():
	doctype = "Agent Performance"
	if not frappe.db.table_exists(doctype):
		return

	has_old = frappe.db.has_column(doctype, "unique_date_confirmed")
	has_new = frappe.db.has_column(doctype, "unique_schedules_walkin")

	if has_old and not has_new:
		frappe.db.rename_column(
			f"tab{doctype}",
			"unique_date_confirmed",
			"unique_schedules_walkin",
		)
	elif not has_old and not has_new:
		frappe.db.sql(
			"""
			ALTER TABLE `tabAgent Performance`
			ADD COLUMN `unique_schedules_walkin` int(11) not null default 0
			"""
		)

	for name in frappe.get_all(
		"DocField",
		filters={"parent": doctype, "fieldname": "unique_date_confirmed"},
		pluck="name",
	):
		frappe.db.set_value(
			"DocField",
			name,
			{"fieldname": "unique_schedules_walkin", "label": "Unique schedules walkin"},
			update_modified=False,
		)

	frappe.clear_cache(doctype=doctype)
