from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.services.crm_lead.lead_service import DuplicateLeadError, LeadService
from frappe.tests.utils import FrappeTestCase


def _doc_mock(**attrs):
	doc = MagicMock()
	store = dict(attrs)
	doc.name = attrs.get("name")

	def get_item(key, default=None):
		return store.get(key, default)

	def set_item(key, value):
		store[key] = value
		setattr(doc, key, value)

	doc.get.side_effect = get_item
	doc.set.side_effect = set_item
	for key, value in attrs.items():
		setattr(doc, key, value)
	return doc


class TestLeadServiceFacebook(FrappeTestCase):
	def setUp(self):
		self.service = LeadService()
		self.facebook_source = SimpleNamespace(name="fb-source-id", source_name="Facebook")

	def _kwargs(self, mobile_no="9100000101", facebook_lead_id="fb-001", **extra):
		raw_data = {
			"id": facebook_lead_id,
			"field_data": [],
			"additional_info": {"campaign_name": "Test Campaign"},
		}
		other_info = {
			"mobile_no": mobile_no,
			"lead_name": extra.pop("lead_name", "FB Lead Name"),
			"facebook_lead_id": facebook_lead_id,
			"facebook_form_id": "form-123",
			**extra,
		}
		return {
			"mobile_no": mobile_no,
			"source": self.facebook_source.source_name,
			"source_id": self.facebook_source.name,
			"facebook_raw_data": raw_data,
			"other_info": other_info,
		}

	@patch.object(LeadService, "_create_lead_with_synced_fields")
	@patch("core.services.crm_lead.lead_service.frappe.db.get_value")
	@patch("core.services.crm_lead.lead_service.frappe.db.exists")
	@patch("core.services.crm_lead.lead_service.parse_phone_number")
	def test_create_facebook_lead_with_additional_info(
		self, mock_parse, mock_exists, mock_get_value, mock_create
	):
		mock_parse.return_value = {"success": True, "national_number": "9100000101"}
		mock_get_value.return_value = None
		mock_exists.return_value = False
		created = SimpleNamespace(
			mobile_no="9100000101",
			facebook_lead_id="fb-001",
			source="Facebook",
			facebook_raw_data={"additional_info": {"campaign_name": "Test Campaign"}},
		)
		mock_create.return_value = created

		doc = self.service.find_or_create_facebook_lead(**self._kwargs())
		self.assertEqual(doc, created)
		mock_create.assert_called_once()

	@patch.object(LeadService, "_create_lead_with_synced_fields")
	@patch("core.services.crm_lead.lead_service.frappe.get_doc")
	@patch("core.services.crm_lead.lead_service.frappe.db.get_value")
	@patch("core.services.crm_lead.lead_service.parse_phone_number")
	def test_duplicate_when_same_facebook_lead_id_on_existing_lead(
		self, mock_parse, mock_get_value, mock_get_doc, mock_create
	):
		mock_parse.return_value = {"success": True, "national_number": "9100000102"}
		mock_get_value.side_effect = ["existing-lead", None]
		mock_get_doc.return_value = _doc_mock(
			name="existing-lead",
			facebook_lead_id="fb-dup-001",
		)

		with self.assertRaises(DuplicateLeadError):
			self.service.find_or_create_facebook_lead(
				**self._kwargs(mobile_no="9100000102", facebook_lead_id="fb-dup-001")
			)
		mock_create.assert_not_called()

	@patch.object(LeadService, "_update_facebook_lead", return_value=True)
	@patch("core.services.crm_lead.lead_service.frappe.get_doc")
	@patch("core.services.crm_lead.lead_service.frappe.db.get_value")
	@patch("core.services.crm_lead.lead_service.parse_phone_number")
	def test_upsert_existing_lead_without_facebook_lead_id(
		self, mock_parse, mock_get_value, mock_get_doc, mock_update
	):
		mock_parse.return_value = {"success": True, "national_number": "9100000103"}
		doc = _doc_mock(
			name="existing-lead",
			lead_name="Keep This Name",
			facebook_lead_id="",
		)
		mock_get_value.side_effect = ["existing-lead", None]
		mock_get_doc.return_value = doc

		result = self.service.find_or_create_facebook_lead(
			**self._kwargs(mobile_no="9100000103", facebook_lead_id="fb-upsert-001")
		)
		self.assertEqual(result, doc)
		mock_update.assert_called_once()
		doc.save.assert_called_once_with(ignore_permissions=True)

	@patch.object(LeadService, "_update_facebook_lead", return_value=True)
	@patch("core.services.crm_lead.lead_service.frappe.get_doc")
	@patch("core.services.crm_lead.lead_service.frappe.db.get_value")
	@patch("core.services.crm_lead.lead_service.parse_phone_number")
	def test_upsert_existing_lead_with_different_facebook_lead_id(
		self, mock_parse, mock_get_value, mock_get_doc, mock_update
	):
		mock_parse.return_value = {"success": True, "national_number": "9100000104"}
		doc = _doc_mock(
			name="existing-lead",
			lead_name="Original Name",
			facebook_lead_id="fb-old-001",
		)
		mock_get_value.side_effect = ["existing-lead", None]
		mock_get_doc.return_value = doc

		result = self.service.find_or_create_facebook_lead(
			**self._kwargs(mobile_no="9100000104", facebook_lead_id="fb-new-002")
		)
		self.assertEqual(result, doc)
		mock_update.assert_called_once()
		doc.save.assert_called_once_with(ignore_permissions=True)

	@patch("core.services.crm_lead.lead_service.frappe.get_doc")
	@patch("core.services.crm_lead.lead_service.frappe.db.get_value")
	@patch("core.services.crm_lead.lead_service.parse_phone_number")
	def test_duplicate_when_facebook_lead_id_owned_by_other_lead(
		self, mock_parse, mock_get_value, mock_get_doc
	):
		mock_parse.return_value = {"success": True, "national_number": "9100000106"}
		mock_get_value.side_effect = ["existing-lead", "other-lead"]
		mock_get_doc.return_value = _doc_mock(
			name="existing-lead",
			facebook_lead_id="",
		)

		with self.assertRaises(DuplicateLeadError):
			self.service.find_or_create_facebook_lead(
				**self._kwargs(mobile_no="9100000106", facebook_lead_id="fb-shared-001")
			)

	def test_apply_synced_lead_fields_preserves_lead_name_on_update(self):
		doc = _doc_mock(
			lead_name="Keep This Name",
			upload_source="Website",
			source=None,
			source_id=None,
			facebook_lead_id="",
			facebook_raw_data=None,
		)

		changed = self.service._apply_synced_lead_fields(
			doc,
			source="Facebook",
			source_id="fb-source-id",
			facebook_raw_data={"id": "fb-new", "additional_info": {"campaign_name": "X"}},
			other_info={
				"lead_name": "Ignored",
				"facebook_lead_id": "fb-new",
				"facebook_form_id": "form-1",
			},
			preserve_lead_name=True,
		)

		self.assertTrue(changed)
		self.assertEqual(doc.lead_name, "Keep This Name")
		self.assertEqual(doc.source, "Facebook")
		self.assertEqual(doc.facebook_lead_id, "fb-new")


class TestFacebookRawDataBuild(FrappeTestCase):
	def test_build_facebook_raw_data_includes_additional_info(self):
		from crm.lead_syncing.doctype.lead_sync_source.facebook import FacebookSyncSource

		sync_source = FacebookSyncSource(access_token="token", form_id="form-1")
		lead = {"id": "fb-123", "created_time": "2026-07-22T10:00:00+0000", "field_data": []}
		additional_info = {"campaign_name": "Summer", "ad_name": "Ad 1"}

		with patch.object(sync_source, "fetch_fb_lead_info", return_value=additional_info):
			raw_data = sync_source.build_facebook_raw_data(lead)

		self.assertEqual(raw_data["id"], "fb-123")
		self.assertEqual(raw_data["additional_info"], additional_info)

	def test_build_facebook_raw_data_continues_when_fetch_fails(self):
		from crm.lead_syncing.doctype.lead_sync_source.facebook import FacebookSyncSource

		sync_source = FacebookSyncSource(access_token="token", form_id="form-1")
		lead = {"id": "fb-456", "field_data": []}

		with patch.object(sync_source, "fetch_fb_lead_info", side_effect=Exception("API down")):
			raw_data = sync_source.build_facebook_raw_data(lead)

		self.assertEqual(raw_data["id"], "fb-456")
		self.assertNotIn("additional_info", raw_data)
