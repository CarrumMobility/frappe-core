import frappe
from core.constants.enums import EnumValues
from crm.fcrm.doctype.crm_lead.crm_lead import apply_default_crm_lead_status_to_doc
from crm.utils import parse_phone_number


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

		phone_number = parse_phone_number(mobile_no)
		if not phone_number.get("success"):
			return None

		mobile_no = phone_number.get("national_number")
		lead_name = frappe.db.get_value(
			EnumValues.ReferenceDocType.CRM_LEAD, {"mobile_no": mobile_no}, "name"
		)

		if lead_name:
			doc = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_name)
			is_new = False
		else:
			doc = frappe.new_doc(EnumValues.ReferenceDocType.CRM_LEAD)
			if not apply_default_crm_lead_status_to_doc(doc):
				frappe.log_error(
					title="findOrCreateLead: no CRM Lead Status",
					message="Configure at least one CRM Lead Status (mark one as default).",
				)
				return None
			doc.mobile_no = mobile_no
			doc.lead_type = EnumValues.LeadType.LEAD
			is_new = True

		if is_new:
			if source is not None and source_id is not None:
				doc.source = source
				doc.source_id = source_id
		elif allow_source_update or self._has_facebook_lead_fields(other_info):
			if source is not None:
				doc.source = source
			if source_id is not None:
				doc.source_id = source_id

		should_update_source = allow_source_update or self._has_facebook_lead_fields(other_info)
		dirty = not is_new and should_update_source and (source is not None or source_id is not None)

		should_apply_facebook_data = is_new or should_update_source
		if facebook_raw_data is not None and should_apply_facebook_data:
			doc.facebook_raw_data = (
				frappe.parse_json(facebook_raw_data)
				if isinstance(facebook_raw_data, str)
				else facebook_raw_data
			)
			dirty = True

		if other_info:
			for key, value in other_info.items():
				doc.set(key, value)
			dirty = True

		if is_new:
			doc.insert(ignore_permissions=True)
		elif dirty:
			doc.save(ignore_permissions=True)

		return doc


lead_service = LeadService()
