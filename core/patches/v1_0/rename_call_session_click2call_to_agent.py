"""Rename Call Session calling_method value Click2Call -> Agent."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	if not frappe.db.has_column("Call Session", "calling_method"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabCall Session`
		SET calling_method = %s
		WHERE calling_method = %s
		""",
		("Agent", "Click2Call"),
	)
	frappe.clear_cache(doctype="Call Session")
