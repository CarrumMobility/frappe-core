from core.api import carrum_accounts
from core.services import logged_requests as requests
import frappe
from frappe import _


def get_chatwoot_ctx(username: str | None = None) -> dict | None:
	"""Load per-user Chatwoot token and inbox from Carrum; account id and base URL from site config."""
	user = username or frappe.session.user
	cfg = carrum_accounts.get_chatwoot_config_by_frappe_user(user)
	if cfg is None:
		return None

	account_id = frappe.conf.get("chatwoot_account_id")
	if account_id is None:
		frappe.throw("Chatwoot account id is not configured (chatwoot_account_id).")
	base_url = (frappe.conf.get("chatwoot_base_url") or "").rstrip("/")

	token = (cfg.token or "").strip()
	if not token:
		return None

	inbox_id = cfg.inboxId
	agent_id = cfg.agentId
	return {
		"api_access_token": token,
		"inbox_id": inbox_id,
		"account_id": account_id,
		"base_url": base_url,
		"agent_id": agent_id,
		"headers": {"api_access_token": token, "Content-Type": "application/json"},
	}


def create_message(conversation_id: int, payload: dict, ctx: dict) -> dict:
	"""
	POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages

	See: https://developers.chatwoot.com/api-reference/messages/create-new-message
	"""
	url = (
		f"{ctx['base_url']}/api/v1/accounts/{ctx['account_id']}"
		f"/conversations/{int(conversation_id)}/messages"
	)
	response = requests.request(
		method="POST",
		url=url,
		headers=ctx["headers"],
		json=payload,
	)
	if not response.ok:
		frappe.throw(_("Failed to send WhatsApp template: {0}").format(response.text))
	return response.json()


def parse_conversation_list_body(body: dict) -> list[dict]:
	inner = body.get("data")
	if isinstance(inner, dict):
		return inner.get("payload") or []
	if isinstance(inner, list):
		return inner
	return []


def get_my_conversations(ctx: dict, page: int = 1) -> dict:
	"""
	GET conversations where assignee_type is me and status is open
	"""
	page_i = max(int(page or 1), 1)
	url = (
		f"{ctx['base_url']}/api/v1/accounts/{ctx['account_id']}/conversations"
		f"?assignee_type=me&status=open&page={page_i}"
	)
	response = requests.request(
		method="GET",
		url=url,
		headers=ctx['headers']
	)

	if not response.ok:
		frappe.throw(_("Failed to get my conversations: {0}").format(response.text))
	return response.json()