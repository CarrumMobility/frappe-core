"""Rename Event.reference_call_log → reference_call_session (DB column + Custom Field).

Preserves existing link values. Sites with only stale Custom Field metadata (no column) still get cleanup + ensure.
"""

import frappe


def execute():
	if (
		frappe.db.has_column("Event", "reference_call_log")
		and not frappe.db.has_column("Event", "reference_call_session")
	):
		for orphan in frappe.get_all(
			"Custom Field",
			filters={"dt": "Event", "fieldname": "reference_call_session"},
			pluck="name",
		):
			frappe.delete_doc("Custom Field", orphan, force=True, ignore_permissions=True)

		old_cf_name = frappe.db.get_value(
			"Custom Field",
			{"dt": "Event", "fieldname": "reference_call_log"},
			"name",
		)
		frappe.db.sql_ddl(
			"ALTER TABLE `tabEvent` CHANGE COLUMN `reference_call_log` `reference_call_session` VARCHAR(140)"
		)
		if old_cf_name:
			frappe.db.sql(
				"UPDATE `tabCustom Field` SET `name`=%s, `fieldname`=%s, `label`=%s, `options`=%s WHERE `name`=%s",
				(
					"Event-reference_call_session",
					"reference_call_session",
					"Reference Call Session",
					"Call Session",
					old_cf_name,
				),
			)
		elif not frappe.db.exists(
			"Custom Field", {"dt": "Event", "fieldname": "reference_call_session"}
		):
			_ensure_reference_call_session_field()
		frappe.db.commit()
		frappe.clear_cache(doctype="Event")
		return

	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Event", "fieldname": "reference_call_log"},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	_ensure_reference_call_session_field()
	frappe.clear_cache(doctype="Event")


def _ensure_reference_call_session_field():
	if frappe.db.exists(
		"Custom Field", {"dt": "Event", "fieldname": "reference_call_session"}
	):
		return

	doc = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Event",
			"module": "Platform",
			"fieldname": "reference_call_session",
			"fieldtype": "Link",
			"label": "Reference Call Session",
			"options": "Call Session",
			"insert_after": "location",
			"in_list_view": 1,
		}
	)
	doc.insert(ignore_permissions=True)
