from core.services.whatsapp.whatsapp_service import WhatsappService
import frappe

whatsappService = WhatsappService()


@frappe.whitelist()
def get_whatsapp_templates():
	user = frappe.session.user
	return whatsappService.get_whatsapp_templates(user=user)


@frappe.whitelist()
def send_whatsapp_template(
	contactId: str,
	conversationId: str | None,
	templateName: str,
	templateContent: str,
	category: str,
	language: str,
	processedParams=None,
):
	if isinstance(processedParams, str):
		processedParams = frappe.parse_json(processedParams)

	return whatsappService.send_whatsapp_template(
		contactId=contactId,
		conversationId=conversationId or None,
		templateName=templateName,
		templateContent=templateContent,
		category=category,
		language=language,
		processedParams=processedParams or {},
	)


@frappe.whitelist()
def get_whatsapp_unread_msg_count():
	user = frappe.session.user
	count = whatsappService.get_whatsapp_unread_msg_count(user=user)

	return {"count": count}