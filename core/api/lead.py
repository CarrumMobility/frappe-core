import frappe
from frappe import _

from core.api import carrum_drivers
from core.constants.enums import EnumValues
from core.services.crm_lead.lead_service import LeadService

logger = frappe.logger("core.api.lead")


lead_service = LeadService()

@frappe.whitelist(methods=['POST'])
def find_or_create_lead(
	mobile_no: str,
	upload_source: str ,
	name: str | None = None,
	source: str | None = None ,
	source_id: str | None = None,
	hub_id: str | None = None,
	hub_name: str | None = None,
):
	lead = lead_service.find_or_create_lead(
		mobile_no=mobile_no,
		source=source,
		source_id=source_id,
		allow_source_update=False,
		other_info={
			"lead_name": name,
			"upload_source": upload_source,
			"hub_id": hub_id,
			"hub_name": hub_name
		},
	)

	return {
		"lead": lead.as_dict(),
	}


@frappe.whitelist()
def update_lead(lead_id: str, lead_updates: dict, portal_updates: dict | None = None, lsq_id: str | None = None):
	lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_id)
	portal_db_updates: dict = portal_updates or {}
	erp_db_changed = False

	for field, value in (lead_updates or {}).items():
		lead.set(field, value)
		erp_db_changed = True

	if erp_db_changed:
		lead.save(ignore_permissions=True)

	if portal_db_updates:
		account_id = (lead.custom_account_id or "").strip()
		if account_id:
			carrum_drivers.update_driver(account_id, portal_db_updates)
		else:
			logger.warning(
				"update_lead: portal_db fields requested (%s) but lead %s has no custom_account_id — skipped",
				list(portal_db_updates),
				lead_id,
			)

	logger.info(
		"update_lead done: lead=%s erp_db_changed=%s portal_db_fields=%s",
		lead_id,
		erp_db_changed,
		list(portal_db_updates),
	)
	return {
		"is_valid": True,
		"data": {
			"lead": lead.as_dict(),
			"lead_updates": lead_updates,
			"portal_updates": portal_updates,
		},
	}


@frappe.whitelist()
def get_lead(lead_id: str, lsq_id: str | None = None):
	logger.info("Getting lead %s (lsq_id=%s)", lead_id, lsq_id)
	lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_id)

	lead_type= lead.get("lead_type")
	portal_details = None
	if lead_type == EnumValues.LeadType.DRIVER:
		portal_details = carrum_drivers.get_portal_driver_detail(lead.name)
		portal_details = portal_details.get("data", {}).get("results", {})

	return {
		"is_valid": True,
		"data": {
			"lead_details": lead.as_dict(),
			"portal_details": portal_details
		}
	}
