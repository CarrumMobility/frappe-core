"""Remove Event.visit_status metadata if the MySQL column was dropped manually.

When `tabEvent.visit_status` is gone but the Custom Field row remains, Frappe still
emits it in INSERT and MySQL returns (1054) Unknown column.
"""

import frappe


def execute():
	frappe.db.delete("Property Setter", {"doc_type": "Event", "field_name": "visit_status"})

	# Do not use `frappe.delete_doc` on Custom Field: `on_trash`/`updatedb` may ALTER-drop a
	# column that is already missing.
	frappe.db.sql("DELETE FROM `tabCustom Field` WHERE `dt` = %s AND `fieldname` = %s", ("Event", "visit_status"))

	if frappe.db.has_column("Event", "visit_status"):
		frappe.db.sql_ddl("ALTER TABLE `tabEvent` DROP COLUMN `visit_status`")

	frappe.clear_cache(doctype="Event")
