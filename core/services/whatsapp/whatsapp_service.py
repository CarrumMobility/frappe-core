from core.api.carrum_whatsapp import get_whatsapp_templates_by_user
from core.integrations.chatwoot import client as chatwoot_client
import frappe
from frappe import _


def _normalize_processed_params(processed_params) -> dict:
	if processed_params is None:
		return {}
	if isinstance(processed_params, str):
		processed_params = frappe.parse_json(processed_params)
	if not isinstance(processed_params, dict):
		frappe.throw(_("processedParams must be an object"))
	return processed_params


def _clean_processed_params(processed_params: dict) -> dict:
	cleaned = {}
	for section in ("body", "header", "footer"):
		values = processed_params.get(section)
		if isinstance(values, dict) and values:
			cleaned[section] = {
				str(key): str(value).strip()
				for key, value in values.items()
				if value is not None and str(value).strip()
			}
	buttons = processed_params.get("buttons")
	if isinstance(buttons, list) and buttons:
		cleaned["buttons"] = [
			{
				"type": str(button.get("type") or "url"),
				"parameter": str(button.get("parameter") or "").strip(),
			}
			for button in buttons
			if isinstance(button, dict) and str(button.get("parameter") or "").strip()
		]
	return cleaned


def build_template_content(template_content: str, processed_params: dict) -> str:
	content = (template_content or "").strip()
	body = processed_params.get("body")
	if not content or not isinstance(body, dict):
		return content

	for key, value in body.items():
		if value is None:
			continue
		content = content.replace(f"{{{{{key}}}}}", str(value).strip())
	return content.strip()


def build_chatwoot_message_payload(
	template_name: str,
	category: str,
	language: str,
	template_content: str,
	processed_params: dict,
) -> dict:
	processed = _clean_processed_params(_normalize_processed_params(processed_params))
	content = build_template_content(template_content, processed) or (template_content or "").strip()

	return {
		"content": content or template_name,
		"template_params": {
			"name": template_name,
			"category": category,
			"language": language,
			"processed_params": processed,
		},
	}


class WhatsappService:
	def send_whatsapp_template(
		self,
		contactId: str,
		conversationId: str | None,
		templateName: str,
		templateContent: str,
		category: str,
		language: str,
		processedParams: dict | None = None,
	):
		ctx = chatwoot_client.get_chatwoot_ctx()
		if ctx is None:
			frappe.throw("Chatwoot is not configured for this user. Check Carrum chatwoot credentials.")

		message_payload = build_chatwoot_message_payload(
			template_name=templateName,
			category=category,
			language=language,
			template_content=templateContent,
			processed_params=processedParams,
		)

		msg_response = chatwoot_client.create_message(
			conversation_id=conversationId,
			payload=message_payload,
			ctx=ctx,
		)
		return {
			"success": True,
			"conversation_id": conversationId,
			"contact_id": int(contactId),
			"message": msg_response,
		}

	def get_whatsapp_templates(self, user: str) -> dict:
		responseData = get_whatsapp_templates_by_user(frappe_user=user)

		dataObj = responseData.get("data") or {}
		inboxId = dataObj.get("inboxId")
		templates = dataObj.get("templates") or []

		finalTemplates = []
		for template in templates:
			parameters = template.get("params") or []
			finalParameters = []
			for param in parameters:
				finalParameters.append(
					{
						"key": param.get("key"),
						"label": param.get("label"),
						"location": param.get("location"),
						"paramType": param.get("paramType"),
						"mediaType": param.get("mediaType"),
						"staticValue": param.get("staticValue"),
					}
				)

			finalTemplates.append(
				{
					"template_id": template.get("id"),
					"template_name": template.get("displayName"),
					"category": template.get("category"),
					"language": template.get("language"),
					"description": template.get("description"),
					"body_preview": template.get("bodyPreview"),
					"parameters": finalParameters,
				}
			)

		return {
			"inboxId": inboxId,
			"templates": finalTemplates,
		}

	def _conversation_page_size(self,meta: dict, payload_len: int) -> int:
		for key in ("per_page", "page_limit", "limit"):
			value = meta.get(key)
			if value is not None:
				try:
					page_size = int(value)
					if page_size > 0:
						return page_size
				except (TypeError, ValueError):
					pass
		if payload_len > 0:
			return max(payload_len, 15)
		return 15


	def _conversation_list_has_more(self,body: dict, payload: list[dict]) -> bool:
		data_block = body.get("data")
		meta = data_block.get("meta") if isinstance(data_block, dict) else {}
		if not isinstance(meta, dict):
			meta = {}

		per_page = self._conversation_page_size(meta, len(payload))
		have_more = len(payload) >= per_page

		for key in ("total_pages", "page_count"):
			total_pages = meta.get(key)
			current_page = meta.get("current_page")
			if total_pages is not None and current_page is not None:
				try:
					have_more = int(current_page) < int(total_pages)
				except (TypeError, ValueError):
					pass
				break

		return have_more

	def get_whatsapp_unread_msg_count(self, user: str) -> int:
		ctx = chatwoot_client.get_chatwoot_ctx(username=user)
		if ctx is None:
			frappe.throw("Chatwoot is not configured for this user. Check Carrum chatwoot credentials.")


		conversations: list[dict] = []

		first_page_response = chatwoot_client.get_my_conversations(ctx=ctx, page=1)
		first_page_conversations = chatwoot_client.parse_conversation_list_body(first_page_response)
		conversations.extend(first_page_conversations)

		if self._conversation_list_has_more(first_page_response, first_page_conversations):
			second_page_response = chatwoot_client.get_my_conversations(ctx=ctx, page=2)
			second_page_conversations = chatwoot_client.parse_conversation_list_body(second_page_response)
			conversations.extend(second_page_conversations)

		return sum(
			1 for conversation in conversations if (conversation.get("unread_count") or 0) > 0
		)

	