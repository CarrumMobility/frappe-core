"""Move UI-added Custom Field custom_hangup_at → standard field hangup_at on Call Session."""

import frappe


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	if frappe.db.has_column("Call Session", "custom_hangup_at") and frappe.db.has_column(
		"Call Session", "hangup_at"
	):
		frappe.db.sql(
			"""UPDATE `tabCall Session`
			SET `hangup_at` = COALESCE(`hangup_at`, `custom_hangup_at`)
			WHERE `custom_hangup_at` IS NOT NULL"""
		)
		frappe.db.commit()

	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Call Session", "fieldname": "custom_hangup_at"},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	frappe.clear_cache(doctype="Call Session")
