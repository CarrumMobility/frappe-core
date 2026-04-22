"""Backfill Event (Visit Date) rows for existing Call Sessions with a scheduled visit."""

import frappe

from core.services.util_service import UtilService


def execute():
	if not frappe.db.table_exists("Call Session"):
		return

	sessions = frappe.db.sql(
		"""
		SELECT name, lead, scheduled_visit_date, disposition_remarks
		FROM `tabCall Session`
		WHERE IFNULL(is_visit_scheduled, 0) = 1
		  AND scheduled_visit_date IS NOT NULL
		  AND COALESCE(lead, '') != ''
		""",
		as_dict=True,
	)
	util = UtilService()
	for s in sessions or []:
		if frappe.db.exists(
			"Event",
			{"reference_call_session": s.name, "event_category": "Visit Date"},
		):
			continue
		try:
			util.create_event_for_visit_date(
				s.lead,
				s.name,
				s.scheduled_visit_date,
				s.disposition_remarks,
			)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"migrate_visit_date_event:{s.name}",
			)
