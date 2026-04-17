"""Rename Call Session UI custom fields custom_disposition_* -> disposition_* (columns + cleanup)."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	old_fields = ("custom_disposition_status", "custom_disposition_remarks")
	new_fields = ("disposition_status", "disposition_remarks")
	in_placeholders = ", ".join(["%s"] * len(old_fields))

	# Remove Custom Field / DocField metadata without running ORM hooks that drop columns.
	frappe.db.sql(
		f"""
		DELETE FROM `tabCustom Field`
		WHERE dt = %s AND fieldname IN ({in_placeholders})
		""",
		("Call Session", *old_fields),
	)
	frappe.db.sql(
		f"""
		DELETE FROM `tabDocField`
		WHERE parent = %s AND fieldname IN ({in_placeholders})
		""",
		("Call Session", *old_fields),
	)

	for old, new in zip(old_fields, new_fields):
		if frappe.db.has_column("Call Session", old) and not frappe.db.has_column("Call Session", new):
			frappe.db.rename_column("Call Session", old, new)

	frappe.clear_cache(doctype="Call Session")
