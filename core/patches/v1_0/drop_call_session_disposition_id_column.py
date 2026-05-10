"""Remove Call Session disposition_id column (value only used for Smartflo API, not persisted)."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	frappe.db.sql(
		"DELETE FROM `tabDocField` WHERE parent = %s AND fieldname = %s",
		("Call Session", "disposition_id"),
	)
	if frappe.db.has_column("Call Session", "disposition_id"):
		# Commit first — ALTER in same tx as DELETE raises ImplicitCommitError.
		frappe.db.sql_ddl("ALTER TABLE `tabCall Session` DROP COLUMN `disposition_id`")

	frappe.clear_cache(doctype="Call Session")
