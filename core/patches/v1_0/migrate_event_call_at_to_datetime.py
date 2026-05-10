"""Normalize Event.call_at for sites where the custom field is Datetime.

`add_event_callback_fields` creates `call_at` as Datetime. This patch is a safe
no-op for new installs; it clears Event cache after schema is in sync.
"""

import frappe


def execute():
	if not frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": "call_at"}):
		return
	frappe.clear_cache(doctype="Event")
