import frappe

from core.api import carrum_accounts
from core.constants.enums import EnumValues
from core.services.whatsapp.whatsapp_service import WhatsappService


class CallWhatsappService:
	def __init__(self,whatsapp_service: WhatsappService):
		self.whatsapp_service = whatsapp_service


	def update_agent_and_lead_in_call_session(self,call_session_id: str, did_number: str):
		carrum_user_details = carrum_accounts.get_users_details_against_did_number(did_number)

		carrum_user_data = carrum_user_details.get('data',{}).get('users',[])[0]
		frappe_user_id = carrum_user_data.get("frappeCred", {}).get("username",None)

		call_session_doc= frappe.get_doc(
			doctype=EnumValues.ReferenceDocType.CALL_SESSION,
			name=call_session_id
		)

		whatsapp_contacts_detail = self.whatsapp_service.get_contacts_by_phone_number(phone_number=did_number,user=frappe.session.user)
		whatsapp_contact_detail = None
		if whatsapp_contacts_detail and len(whatsapp_contacts_detail) > 0:
			whatsapp_contact_detail = whatsapp_contacts_detail[0]

		lead_id = whatsapp_contact_detail.get("driver_id")
		call_session_doc.set("agent", frappe_user_id)
		call_session_doc.set("lead", lead_id)
		call_session_doc.save(ignore_permissions=True)

		return {
			"agent": frappe_user_id,
			"lead": lead_id,
			"call_session_id": call_session_id
		}

def exposed_update_call_session_with_whatsapp_contact_detail(call_session_id: str, whatsapp_contact_detail: dict):
	call_whatsapp_service = CallWhatsappService(whatsapp_service=WhatsappService())
	return call_whatsapp_service.update_agent_and_lead_in_call_session(call_session_id=call_session_id, did_number=whatsapp_contact_detail.get("phone"))

__all__ = ['CallWhatsappService']
