# Copyright (c) 2026, core and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from core.platform.doctype.lead_sync_entry.lead_sync_entry import (
	LeadSyncEntry,
	find_lead_sync_entry_name_by_vendor_id,
)


def _make_lead_sync_entry(**overrides):
	data = {
		"doctype": "Lead Sync Entry",
		"vendor_id": "fb-dup-vendor-001",
		"vendor_name": "Facebook",
		"lead_sync_source": "test-lead-sync-source",
		"submitted_at": "2026-07-23 09:33:38",
		"raw": {"id": "fb-dup-vendor-001"},
	}
	data.update(overrides)
	return frappe.get_doc(data)


class TestLeadSyncEntry(FrappeTestCase):
	def test_validate_rejects_duplicate_vendor_id(self):
		first = _make_lead_sync_entry(vendor_id="fb-dup-vendor-001")
		first.insert(ignore_permissions=True, ignore_links=True)

		duplicate = _make_lead_sync_entry(vendor_id="fb-dup-vendor-001")
		with self.assertRaises(frappe.DuplicateEntryError):
			duplicate.insert(ignore_permissions=True, ignore_links=True)

	def test_validate_skips_duplicate_check_for_empty_vendor_id(self):
		doc = LeadSyncEntry({"doctype": "Lead Sync Entry", "vendor_id": None})
		doc.validate_unique_vendor_id()

	def test_find_prefers_linked_entry_when_duplicates_exist(self):
		older = _make_lead_sync_entry(vendor_id="fb-prefer-linked-001")
		older.insert(ignore_permissions=True, ignore_links=True)

		# Simulate legacy duplicate rows that existed before app-level validation.
		frappe.db.sql(
			"""
			INSERT INTO `tabLead Sync Entry`
				(name, owner, creation, modified, modified_by, docstatus, idx,
				 vendor_id, vendor_name, lead_sync_source, raw, lead_id, submitted_at)
			VALUES
				(%s, %s, NOW(), NOW(), %s, 0, 0, %s, %s, %s, %s, %s, %s)
			""",
			(
				"legacy-linked-entry",
				frappe.session.user,
				frappe.session.user,
				"fb-prefer-linked-001",
				"Facebook",
				"test-lead-sync-source",
				'{"id": "fb-prefer-linked-001"}',
				"CRM-LEAD-LINKED",
				"2026-07-23 09:33:38",
			),
		)

		self.assertEqual(
			find_lead_sync_entry_name_by_vendor_id("fb-prefer-linked-001", prefer_linked=True),
			"legacy-linked-entry",
		)
