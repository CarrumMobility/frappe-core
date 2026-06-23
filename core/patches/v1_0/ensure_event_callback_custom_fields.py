"""Re-create Event callback/visit Custom Field records when DB columns exist but metadata was lost."""

import frappe

_EVENT_CALLBACK_FIELDS = (
	"reference_call_session",
	"call_at",
	"callback_status",
	"disposition_status",
	"sub_disposition_status",
	"disposition_remarks",
	"crm_lead_name",
	"preferred_scheme_1",
)


def execute():
	_ensure_event_category_index()
	_ensure_event_callback_custom_fields()
	frappe.clear_cache(doctype="Event")


def _ensure_event_category_index():
	cols = frappe.db.get_table_columns("Event") or []
	if "event_category" not in cols:
		return

	if frappe.db.get_column_index("tabEvent", "event_category"):
		return

	index_name = frappe.db.get_index_name(["event_category"])
	frappe.db.commit()
	if frappe.db.db_type == "mariadb":
		frappe.db.sql_ddl(
			f"ALTER TABLE `tabEvent` "
			f"ADD INDEX IF NOT EXISTS `{index_name}` (`event_category`) USING BTREE"
		)
	else:
		frappe.db.add_index("Event", ["event_category"], index_name)


def _ensure_event_callback_custom_fields():
	cols = set(frappe.db.get_table_columns("Event") or [])
	if not cols.intersection(_EVENT_CALLBACK_FIELDS):
		return

	missing = [
		fieldname
		for fieldname in _EVENT_CALLBACK_FIELDS
		if fieldname in cols
		and not frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": fieldname})
	]
	if not missing:
		return

	from core.patches.v1_0.add_event_callback_fields import execute as ensure_callback_fields
	from crm.patches.v1_0.add_event_crm_lead_snapshot_fields import execute as ensure_snapshot_fields
	from crm.patches.v1_0.add_event_disposition_status_fields import execute as ensure_disposition_fields

	ensure_callback_fields()
	ensure_disposition_fields()
	ensure_snapshot_fields()
