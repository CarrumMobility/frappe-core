"""Drop legacy unique_date_confirmed after unique_schedules_walkin exists."""

import frappe


def execute():
	doctype = "Agent Performance"
	if not frappe.db.table_exists(doctype):
		return

	has_old = frappe.db.has_column(doctype, "unique_date_confirmed")
	has_new = frappe.db.has_column(doctype, "unique_schedules_walkin")
	if not has_old:
		return

	if has_new:
		frappe.db.sql(
			"""
			UPDATE `tabAgent Performance`
			SET `unique_schedules_walkin` = `unique_date_confirmed`
			WHERE IFNULL(`unique_schedules_walkin`, 0) = 0
			  AND IFNULL(`unique_date_confirmed`, 0) != 0
			"""
		)

	frappe.db.commit()
	frappe.db.sql_ddl(
		"ALTER TABLE `tabAgent Performance` DROP COLUMN `unique_date_confirmed`"
	)
	frappe.clear_cache(doctype=doctype)
