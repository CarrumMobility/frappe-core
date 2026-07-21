import frappe
from core.constants.enums import EnumValues
from crm.fcrm.doctype.crm_lead.crm_lead import apply_default_crm_lead_status_to_doc
from crm.utils import parse_phone_number


class DuplicateLeadError(frappe.ValidationError):
	pass


class LeadService:
	def __init__(self):
		pass

	@staticmethod
	def _has_facebook_lead_fields(other_info: dict | None) -> bool:
		return bool(
			other_info and ("facebook_lead_id" in other_info or "facebook_form_id" in other_info)
		)

	@staticmethod
	def get_lead_source_row(
		source_name: str,
		purpose: str | None = None,
	) -> dict | None:
		"""Resolve CRM Lead Source by display name and optional purpose."""
		source_name = (source_name or "").strip()
		if not source_name:
			return None
		filters = {"source_name": source_name}
		if purpose:
			filters["purpose"] = purpose
		return frappe.db.get_value(
			EnumValues.ReferenceDocType.LEAD_SOURCE,
			filters,
			["name", "source_name"],
			as_dict=True,
		)

	def find_or_create_lead(
		self,
		mobile_no: str,
		source: str | None = None,
		source_id: str | None = None,
		allow_source_update: bool = False,
		facebook_raw_data: dict | str | None = None,
		other_info: dict | None = None,
	):
		if not mobile_no:
			return None

		parsed = parse_phone_number(mobile_no)
		if not parsed.get("success"):
			return None

		mobile_no = parsed.get("national_number")
		lead_name = frappe.db.get_value(
			EnumValues.ReferenceDocType.CRM_LEAD, {"mobile_no": mobile_no}, "name"
		)

		if lead_name:
			doc = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_name)
			if self._update_existing_lead(
				doc,
				source=source,
				source_id=source_id,
				allow_source_update=allow_source_update,
				facebook_raw_data=facebook_raw_data,
				other_info=other_info,
			):
				doc.save(ignore_permissions=True)
			return doc

		return self._create_lead_with_synced_fields(
			mobile_no,
			source=source,
			source_id=source_id,
			facebook_raw_data=facebook_raw_data,
			other_info=other_info,
		)

	def find_or_create_facebook_lead(
		self,
		mobile_no: str,
		source: str | None = None,
		source_id: str | None = None,
		facebook_raw_data: dict | str | None = None,
		other_info: dict | None = None,
	):
		if not mobile_no:
			frappe.throw(frappe._("Mobile number is required"), frappe.ValidationError)

		parsed = parse_phone_number(mobile_no)
		if not parsed.get("success"):
			frappe.throw(
				frappe._("Invalid mobile number: {0}").format(mobile_no),
				frappe.ValidationError,
			)

		mobile_no = parsed.get("national_number")
		facebook_lead_id = str((other_info or {}).get("facebook_lead_id") or "").strip()

		if frappe.db.exists(EnumValues.ReferenceDocType.CRM_LEAD, {"mobile_no": mobile_no}):
			raise DuplicateLeadError(
				frappe._("A CRM Lead already exists with mobile number {0}").format(mobile_no)
			)

		if facebook_lead_id and frappe.db.exists(
			EnumValues.ReferenceDocType.CRM_LEAD, {"facebook_lead_id": facebook_lead_id}
		):
			raise DuplicateLeadError(
				frappe._("A CRM Lead already exists with Facebook lead ID {0}").format(facebook_lead_id)
			)

		return self._create_lead_with_synced_fields(
			mobile_no,
			source=source,
			source_id=source_id,
			facebook_raw_data=facebook_raw_data,
			other_info=other_info,
		)

	def _create_lead_with_synced_fields(
		self,
		mobile_no: str,
		*,
		source: str | None,
		source_id: str | None,
		facebook_raw_data: dict | str | None,
		other_info: dict | None,
	):
		doc = frappe.new_doc(EnumValues.ReferenceDocType.CRM_LEAD)
		if not apply_default_crm_lead_status_to_doc(doc):
			frappe.log_error(
				title="findOrCreateLead: no CRM Lead Status",
				message="Configure at least one CRM Lead Status (mark one as default).",
			)
			frappe.throw(
				frappe._("No default CRM Lead Status is configured"),
				frappe.ValidationError,
			)

		doc.mobile_no = mobile_no
		doc.lead_type = EnumValues.LeadType.LEAD
		doc.insert(ignore_permissions=True)

		if self._apply_synced_lead_fields(
			doc,
			source=source,
			source_id=source_id,
			facebook_raw_data=facebook_raw_data,
			other_info=other_info,
		):
			doc.save(ignore_permissions=True)

		return doc

	@staticmethod
	def _should_update_facebook_raw_data(
		doc,
		other_info: dict | None,
		facebook_raw_data: dict | str | None,
	) -> bool:
		if facebook_raw_data is None:
			return False

		incoming_fb_lead_id = str((other_info or {}).get("facebook_lead_id") or "").strip()
		existing_fb_lead_id = str(doc.get("facebook_lead_id") or "").strip()
		return incoming_fb_lead_id != existing_fb_lead_id

	def _apply_synced_lead_fields(
		self,
		doc,
		*,
		source: str | None,
		source_id: str | None,
		facebook_raw_data: dict | str | None,
		other_info: dict | None,
	) -> bool:
		dirty = False

		if source is not None:
			doc.source = source
			dirty = True
		if source_id is not None:
			doc.source_id = source_id
			dirty = True

		if self._should_update_facebook_raw_data(doc, other_info, facebook_raw_data):
			doc.facebook_raw_data = (
				frappe.parse_json(facebook_raw_data)
				if isinstance(facebook_raw_data, str)
				else facebook_raw_data
			)
			dirty = True

		if other_info:
			for key, value in other_info.items():
				if key == "mobile_no":
					continue
				doc.set(key, value)
				dirty = True

		return dirty

	def _update_existing_lead(
		self,
		doc,
		*,
		source: str | None,
		source_id: str | None,
		allow_source_update: bool,
		facebook_raw_data: dict | str | None,
		other_info: dict | None,
	) -> bool:
		should_update = allow_source_update or self._has_facebook_lead_fields(other_info)
		if not should_update:
			return False

		return self._apply_synced_lead_fields(
			doc,
			source=source,
			source_id=source_id,
			facebook_raw_data=facebook_raw_data,
			other_info=other_info,
		)


lead_service = LeadService()
