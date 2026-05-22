"""Rename missed Call Session status values for stored rows."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	if not frappe.db.has_column("Call Session", "status"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabCall Session`
		SET status = CASE
			WHEN status = %s THEN %s
			WHEN status = %s THEN %s
			ELSE status
		END
		WHERE status IN (%s, %s)
		""",
		("NOT_CONNECTED", "OB Missed", "MISSED", "IB Missed", "NOT_CONNECTED", "MISSED"),
	)
	frappe.clear_cache(doctype="Call Session")
