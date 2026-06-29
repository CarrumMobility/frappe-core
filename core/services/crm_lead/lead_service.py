import frappe
from core.constants.enums import EnumValues
from crm.fcrm.doctype.crm_lead.crm_lead import apply_default_crm_lead_status_to_doc
from crm.utils import parse_phone_number


class LeadService:
	def __init__(self):
		pass

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
		elif allow_source_update:
			if source is not None:
				doc.source = source
			if source_id is not None:
				doc.source_id = source_id

		dirty = not is_new and (allow_source_update and (source is not None or source_id is not None))

		if facebook_raw_data is not None:
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
