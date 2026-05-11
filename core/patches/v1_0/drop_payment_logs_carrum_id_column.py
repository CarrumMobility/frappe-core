"""Remove redundant ``payment_logs.carrum_id`` (duplicate of ``name``); naming uses ``prompt`` + transaction id."""

import frappe


def execute():
	dt = "payment_logs"
	table = "tabpayment_logs"

	frappe.db.sql(
		"DELETE FROM `tabDocField` WHERE parent = %s AND fieldname = %s",
		(dt, "carrum_id"),
	)

	if not frappe.db.has_column(dt, "carrum_id"):
		frappe.clear_cache(doctype=dt)
		return

	idx_rows = frappe.db.sql(
		f"SHOW INDEX FROM `{table}` WHERE Column_name = %s",
		("carrum_id",),
		as_dict=True,
	) or []
	seen_keys = set()
	for row in idx_rows:
		key = (row.get("Key_name") or "").strip()
		if key and key != "PRIMARY" and key not in seen_keys:
			seen_keys.add(key)
			frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP INDEX `{key}`")

	frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `carrum_id`")

	frappe.clear_cache(doctype=dt)
