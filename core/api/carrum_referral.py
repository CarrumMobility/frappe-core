from urllib.parse import quote, urlencode

from core.services import logged_requests as requests

import frappe
from frappe import _

from core.services.carrum_client import CarrumHttpClient

logger = frappe.logger("core::carrum_referral")


def create_lead_referral_on_portal(
	refereeId,
	referrerId,
	hubId,
	agentReferrerId=None,
	configId=None,
	base_url=None,
	token=None,
):
	"""
	POST ``/api/v1/referral-rewards`` when both referee and referrer CRM leads are known.

	Payload includes ``refereeId``, ``referrerId``, and ``hubId``.
	``referrerId`` / ``hubId`` may be None (sent as JSON null).
	``configId`` is sent for vendor referral scheme configuration when provided.

	Returns the same framed dict as ``CarrumHttpClient.request`` (``success``, ``data`` or ``error``,
	``request_url``, etc.).
	"""
	referee_key = (refereeId or "").strip() if refereeId is not None else ""
	if not referee_key:
		return {
			"success": False,
			"error": _("Referee id is required"),
			"request_url": None,
		}

	payload = {
		"refereeId": referee_key,
		"referrerId": referrerId,
		"hubId": hubId,
	}
	if(agentReferrerId):
		payload["agentReferrerId"] = agentReferrerId
	if configId:
		payload["configId"] = str(configId).strip()
	print(payload,'payload')
	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="POST",
		path="/api/v1/referral-rewards",
		json=payload,
		log_tag="create-lead-referral",
	)


def create_referral_on_portal(
	refereeId,
	agentReferrerId,
	hubId,
	referrerId=None,
	base_url=None,
	token=None,
):
	"""
	Create a referral on the Carrum portal (POST ``/api/v1/referral-rewards``).

	Payload: ``refereeId``, ``agentReferrerId``, ``hubId`` (may be JSON null),
	optional ``referrerId`` when provided.

	Returns the same framed dict as ``CarrumHttpClient.request`` (``success``, ``data`` or ``error``,
	``request_url``, etc.).
	"""
	referee_key = (refereeId or "").strip() if refereeId is not None else ""
	if not referee_key:
		return {
			"success": False,
			"error": _("Referee id is required"),
			"request_url": None,
		}

	agent_key = (
		str(agentReferrerId).strip() if agentReferrerId is not None else ""
	)
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent referrer id is required"),
			"request_url": None,
		}

	payload = {
		"refereeId": referee_key,
		"agentReferrerId": agent_key,
		"hubId": hubId,
	}
	if referrerId:
		rid = str(referrerId).strip()
		if rid:
			payload["referrerId"] = rid

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="POST",
		path="/api/v1/referral-rewards",
		json=payload,
		log_tag="create-referral",
	)



def get_lead_referrals_from_carrum_portal(referrer_id):
	"""
	GET referrals for a referrer from Carrum.

	URL: ``{carrum_base_url}/api/v1/referral-rewards/referrer/{referrer_id}``
	"""
	referrer_id = (referrer_id or "").strip()
	if not referrer_id:
		return {
			"success": False,
			"error": _("Referrer id is required"),
		}
	referrer_segment = quote(referrer_id, safe="")
	client = CarrumHttpClient(timeout=30)
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/referrer/{referrer_segment}",
		log_tag="lead-referrals-referrer-list",
	)


def get_agent_referral_list(
	agent_referrer_id,
	referrerId=None,
	page=1,
	limit=20,
	reward_type="AGENT_REFERRAL",
	base_url=None,
	token=None,
):
	"""
	``base_url`` / ``token`` override ``frappe.conf`` ``carrum_base_url`` / ``carrum_token`` when set.
	Omit them (``None``) to use bench defaults.
	"""
	agent_referrer_id = (agent_referrer_id or "").strip()
	if not agent_referrer_id:
		return {
			"success": False,
			"error": _("Agent referrer id is required"),
		}

	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	agent_segment = quote(agent_referrer_id, safe="")
	params = {
		"rewardType": reward_type,
		"page": page,
		"limit": limit,
	}
	if referrerId:
		params["referrerId"] = referrerId
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/agent/{agent_segment}",
		params=params,
		log_tag="agent-referral-list",
	)


def get_wallet_transactions_from_portal(
	wallet_id,
	page=1,
	limit=20,
	base_url=None,
	token=None,
):
	"""
	GET ``/api/v1/referral-rewards/wallets/{walletId}/transactions`` from Carrum.

	Query: ``page``, ``limit``.

	Returns the same framed dict as ``CarrumHttpClient.request``.
	"""
	wallet_key = (str(wallet_id).strip() if wallet_id is not None else "") or ""
	if not wallet_key:
		return {
			"success": False,
			"error": _("Wallet id is required"),
			"request_url": None,
		}

	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20
	if limit > 100:
		limit = 100

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	wallet_segment = quote(wallet_key, safe="")
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/reward-ledger/{wallet_segment}/transactions",
		params={"page": page, "limit": limit},
		log_tag="wallet-transactions",
	)


def get_lead_referred_by_details_from_portal(lead_id, base_url=None, token=None):
	"""
	GET referee referral details from Carrum (referrer context for a referee lead).

	URL: ``{carrum_base_url}/api/v1/referral-rewards/referee/{lead_id}``

	``lead_id`` is the path segment Carrum expects (typically CRM Lead name or account id).

	``base_url`` / ``token`` default to ``frappe.conf`` when omitted (see ``CarrumHttpClient``).

	Returns:
		Same framed dict as ``CarrumHttpClient.request``: ``success``, ``status_code``, ``data``,
		``request_url`` on success; ``error`` / ``response`` on failure.
	"""
	lead_id = (lead_id or "").strip()
	if not lead_id:
		return {
			"success": False,
			"error": _("Lead id is required"),
			"request_url": None,
		}

	lead_segment = quote(lead_id, safe="")
	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/referee/{lead_segment}",
		log_tag="referee-referred-by-details",
	)


def remove_lead_referrer_from_portal(referee_id=None, base_url=None, token=None):
	"""
	Remove referred-by mapping for a referee lead on Carrum.

	Calls ``DELETE /api/v1/referral-rewards/referee/{lead_id}``.
	"""
	lead_key = (referee_id or "").strip() if referee_id is not None else ""
	if not lead_key:
		return {
			"success": False,
			"error": _("Lead id is required"),
			"request_url": None,
		}

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	lead_segment = quote(lead_key, safe="")
	return client.request(
		method="DELETE",
		path=f"/api/v1/referral-rewards/referee/{lead_segment}",
		log_tag="remove-referrer",
	)


def fetch_referee_milestones_from_carrum(
	lead_id,
	page=1,
	limit=20,
	reward_type="AGENT_REFERRAL",
):
	"""
	GET milestone journey for a referee (CRM Lead id) from Carrum.

	URL: ``{carrum_base_url}/api/v1/referral-rewards/referee/{lead_id}/milestones``
	Query: ``rewardType``, ``page``, ``limit``.
	"""
	lead_id = (lead_id or "").strip()
	if not lead_id:
		return {
			"success": False,
			"error": _("Lead id is required"),
		}

	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20

	base_url = (frappe.conf.get("carrum_base_url") or "").strip().rstrip("/")
	if not base_url:
		return {
			"success": False,
			"error": _("Carrum base URL is not configured (carrum_base_url)"),
		}

	token = frappe.conf.get("carrum_token")
	if not token:
		return {
			"success": False,
			"error": _("Carrum token is not configured (carrum_token)"),
		}

	lead_segment = quote(lead_id, safe="")
	query = urlencode(
		{
			"rewardType": reward_type,
			"page": page,
			"limit": limit,
		}
	)
	url = f"{base_url}/api/v1/referral-rewards/referee/{lead_segment}/milestones?{query}"

	headers = {
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referee milestones timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to milestone service timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referee milestones connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to milestone service"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referee milestones request error: %s", err)
		return {
			"success": False,
			"error": _("Milestone request failed: {0}").format(str(err)),
		}

	try:
		response.raise_for_status()
	except requests.exceptions.HTTPError as err:
		text = ""
		status = getattr(err.response, "status_code", None)
		if err.response is not None:
			try:
				text = (err.response.text or "")[:2000]
			except Exception:
				text = ""
		logger.error(
			"Carrum referee milestones HTTP error status=%s body=%s",
			status,
			text,
		)
		return {
			"success": False,
			"status_code": status,
			"error": str(err),
			"response": text or None,
		}

	try:
		data = response.json()
	except ValueError:
		logger.error("Carrum referee milestones invalid JSON status=%s", response.status_code)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from milestone service"),
			"response": (response.text or "")[:2000] or None,
		}

	return {
		"success": True,
		"status_code": response.status_code,
		"data": data.get("data", {}),
	}


def get_cumulative_referral_list_from_portal(
	page=1,
	limit=20,
	reward_type="AGENT_REFERRAL",
	agent_id=None,
	base_url=None,
	token=None,
	referrer_id=None,
):
	"""
	GET cumulative referral list from Carrum.

	``GET {carrum_base_url}/api/v1/referral-rewards/hub-summary`` with query
	``loggedInUserId``, ``rewardType``, ``page``, and ``limit``.

	Returns the same framed dict as ``CarrumHttpClient.request``.
	"""
	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20

	agent_key = (str(agent_id).strip() if agent_id is not None else "")
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id is required"),
			"request_url": None,
		}

	params = {
		# "loggedInUserId": agent_key,
		"rewardType": reward_type,
		"page": page,
		"limit": limit,
	}
	if(referrer_id):
		params["referrerId"] = referrer_id

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/agent/{agent_key}",
		params=params,
		log_tag="hub-summary",
	)


def get_carrum_employee_referrals(
	page=1,
	limit=20,
	reward_type="AGENT_REFERRAL",
	agent_id=None,
	base_url=None,
	token=None,
	referrer_id=None,
):
	"""
	GET Carrum employee / hub-summary referral list (same HTTP behaviour as
	``get_cumulative_referral_list_from_portal`` — inlined for CRM employee referrals).

	``GET {carrum_base_url}/api/v1/referral-rewards/agent/{agent_id}`` with query
	``rewardType`` (default ``AGENT_REFERRAL``), ``page``, ``limit``, optional ``referrerId``.

	Returns the same framed dict as ``CarrumHttpClient.request``.
	"""
	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20

	agent_key = (str(agent_id).strip() if agent_id is not None else "")
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id is required"),
			"request_url": None,
		}

	params = {
		"rewardType": reward_type,
		"page": page,
		"limit": limit,
		"loggedInUserId":agent_key
	}
	if referrer_id:
		params["referrerId"] = referrer_id

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/hub-summary",
		params=params,
		log_tag="hub-summary",
	)


def carrum_referral_breakdown(
	page=1,
	limit=20,
	reward_type="REFERRAL",
	agent_id=None,
	base_url=None,
	token=None,
	referrer_id=None,
):
	"""
	GET referral breakdown list from Carrum (same HTTP behaviour as
	``get_cumulative_referral_list_from_portal``; default ``rewardType`` is ``REFERRAL``).

	``GET {carrum_base_url}/api/v1/referral-rewards/agent/{agent_id}`` with query
	``rewardType``, ``page``, ``limit``, and optional ``referrerId``.

	Returns the same framed dict as ``CarrumHttpClient.request``.
	"""
	try:
		page = int(page)
		limit = int(limit)
	except (TypeError, ValueError):
		page, limit = 1, 20
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20

	agent_key = (str(agent_id).strip() if agent_id is not None else "")
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id is required"),
			"request_url": None,
		}

	params = {
		"rewardType": reward_type,
		"page": page,
		"limit": limit,
	}
	if referrer_id:
		params["referrerId"] = referrer_id

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="GET",
		path=f"/api/v1/referral-rewards/agent/{agent_key}",
		params=params,
		log_tag="hub-summary",
	)


def approve_referral_on_carrum_portal(
	amount=None,
	remark=None,
	wallet_id=None,
	agent_id=None,
	base_url=None,
	token=None,
):
	"""
	Wallet approval on the Carrum referral portal.

	``POST /api/v1/referral-rewards/wallets/{walletId}/approve`` with query
	``loggedInUserId`` = ``agent_id``. JSON body: ``approvedAmount``, optional ``remarks``.

	Returns:
		Same framed dict as ``CarrumHttpClient.request``.
	"""
	amount_str = str(amount).strip() if amount is not None else ""
	if not amount_str:
		return {
			"success": False,
			"error": _("Approval amount is required"),
			"request_url": None,
		}

	try:
		approved_amount = float(amount_str)
	except (TypeError, ValueError):
		approved_amount = amount_str

	remark_str = str(remark).strip() if remark is not None else ""

	wallet_key = (str(wallet_id).strip() if wallet_id is not None else "") or ""
	if not wallet_key:
		return {
			"success": False,
			"error": _("Wallet id is required"),
			"request_url": None,
		}

	agent_key = (str(agent_id).strip() if agent_id is not None else "") or ""
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id (loggedInUserId) is required"),
			"request_url": None,
		}

	payload = {"amount": int(approved_amount)}
	if remark_str:
		payload["remarks"] = remark_str

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	wallet_segment = quote(wallet_key, safe="")
	return client.request(
		method="POST",
		path=f"/api/v1/referral-rewards/reward-ledger/{wallet_segment}/approve",
		params={"loggedInUserId": agent_key},
		json=payload,
		log_tag="approve-wallet-referral",
	)


def approve_reward_ledger_on_carrum_portal(
	ledger_id=None,
	logged_in_user_id=None,
	amount=None,
	remarks=None,
	adjust_in_hissab=None,
	base_url=None,
	token=None,
):
	"""
	Approve a reward ledger entry on the Carrum referral portal.

	``POST /api/v1/referral-rewards/reward-ledger/{ledgerId}/approve``
	with query ``loggedInUserId`` and JSON body ``amount``, optional ``remarks``.

	Returns:
		Same framed dict as ``CarrumHttpClient.request``.
	"""
	ledger_key = (str(ledger_id).strip() if ledger_id is not None else "") or ""
	if not ledger_key:
		return {
			"success": False,
			"error": _("Ledger id is required"),
			"request_url": None,
		}

	user_key = (
		str(logged_in_user_id).strip() if logged_in_user_id is not None else ""
	) or ""
	if not user_key:
		return {
			"success": False,
			"error": _("Logged in user id is required"),
			"request_url": None,
		}

	amount_str = str(amount).strip() if amount is not None else ""
	if not amount_str:
		return {
			"success": False,
			"error": _("Approval amount is required"),
			"request_url": None,
		}

	try:
		approval_amount = float(amount_str)
	except (TypeError, ValueError):
		return {
			"success": False,
			"error": _("Approval amount must be a valid number"),
			"request_url": None,
		}

	payload = {
		"amount": int(approval_amount)
		if approval_amount.is_integer()
		else approval_amount
	}
	remarks_str = str(remarks).strip() if remarks is not None else ""
	if remarks_str:
		payload["remarks"] = remarks_str
	if adjust_in_hissab in (True, 1, "1", "true", "True"):
		payload["adjustInHissab"] = True

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="POST",
		path=f"/api/v1/referral-rewards/reward-ledger/{quote(ledger_key, safe='')}/approve",
		params={"loggedInUserId": user_key},
		json=payload,
		log_tag="approve-reward-ledger",
	)


def approve_referral_by_referral_id_on_carrum_portal(
	amount=None,
	referral_id=None,
	milestone=None,
	remark=None,
	rewardType="AGENT_REFERRAL",
	user_name=None,
	base_url=None,
	token=None,
):
	"""
	Per-referee approval: ``POST .../referral-rewards/{referralId}/approve?userName=...``.

	Used by CRM lead-based referral approval (e.g. ``approve_referral_dummy``).
	"""
	amount_str = str(amount).strip() if amount is not None else ""
	if not amount_str:
		return {
			"success": False,
			"error": _("Approval amount is required"),
			"request_url": None,
		}

	try:
		approved_amount = float(amount_str)
	except (TypeError, ValueError):
		approved_amount = amount_str

	remark_str = str(remark).strip() if remark is not None else ""

	referral_key = (str(referral_id).strip() if referral_id is not None else "") or ""
	if not referral_key:
		return {
			"success": False,
			"error": _("Referee id is required"),
			"request_url": None,
		}

	milestone_str = str(milestone).strip() if milestone is not None else ""
	if not milestone_str:
		return {
			"success": False,
			"error": _("Milestone id is required"),
			"request_url": None,
		}

	try:
		milestone_days = int(float(milestone_str))
	except (TypeError, ValueError):
		return {
			"success": False,
			"error": _("Milestone must be a valid number"),
			"request_url": None,
		}

	user_key = (str(user_name).strip() if user_name is not None else "") or ""
	if not user_key:
		user_key = (frappe.session.user or "").strip()
	if not user_key:
		return {
			"success": False,
			"error": _("User name is required"),
			"request_url": None,
		}

	payload = {
		"rewardType": rewardType,
		"approvedAmount": approved_amount,
		"milestoneDays": milestone_days,
	}
	if remark_str:
		payload["remarks"] = remark_str

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	referral_segment = quote(referral_key, safe="")
	return client.request(
		method="POST",
		path=f"/api/v1/referral-rewards/{referral_segment}/approve",
		params={"userName": user_key},
		json=payload,
		log_tag="approve-referral",
	)




def reject_referral_on_carrum_portal(
	milestone=None,
	user_name=None,
	remark=None,
	referral_id=None,
	rewardType="AGENT_REFERRAL",
):
	"""
	POST reject request to the Carrum referral portal.

	URL: ``{carrum_base_url}/api/v1/referral-rewards/reject?userName=...``

	Query:
		``userName``: Frappe user name (defaults to ``frappe.session.user``).

	JSON body:
		``refereeId``: CRM Lead / referee identifier (same as ``approve``).
		``milestoneId``: milestone to reject.
		``remark``: optional note (included when non-empty).

	Returns:
		Same framed dict as ``CarrumHttpClient.request``.
	"""
	referral_id = (referral_id or "").strip()
	if not referral_id:
		return {
			"success": False,
			"error": _("Referee id is required"),
		}

	milestone_str = str(milestone).strip() if milestone is not None else ""
	if not milestone_str:
		return {
			"success": False,
			"error": _("Milestone id is required"),
		}

	user_name = (user_name or frappe.session.user or "").strip()
	if not user_name:
		return {
			"success": False,
			"error": _("User name is required"),
		}

	base_url = (frappe.conf.get("carrum_base_url") or "").strip().rstrip("/")
	if not base_url:
		return {
			"success": False,
			"error": _("Carrum base URL is not configured (carrum_base_url)"),
		}

	token = frappe.conf.get("carrum_token")
	if not token:
		return {
			"success": False,
			"error": _("Carrum token is not configured (carrum_token)"),
		}

	query = urlencode({"userName": user_name})
	url = f"{base_url}/api/v1/referral-rewards/{referral_id}/reject?{query}"

	payload = {
		"milestoneDays": int(milestone_str),
		"rewardType": rewardType,
	}
	remark_str = str(remark).strip() if remark is not None else ""
	if remark_str:
		payload["reason"] = remark_str

	headers = {
		"Content-Type": "application/json",
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.post(url, json=payload, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referral reject timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral portal timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referral reject connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral portal"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referral reject request error: %s", err)
		return {
			"success": False,
			"error": _("Referral portal request failed: {0}").format(str(err)),
		}

	try:
		response.raise_for_status()
	except requests.exceptions.HTTPError as err:
		text = ""
		status = getattr(err.response, "status_code", None)
		if err.response is not None:
			try:
				text = (err.response.text or "")[:2000]
			except Exception:
				text = ""
		logger.error(
			"Carrum referral reject HTTP error status=%s body=%s",
			status,
			text,
		)
		return {
			"success": False,
			"status_code": status,
			"error": str(err),
			"response": text or None,
		}

	if response.status_code == 204 or not (response.text or "").strip():
		return {
			"success": True,
			"status_code": response.status_code,
			"data": {"message": _("Referral request rejected")},
			"message": _("Referral request rejected"),
		}

	try:
		data = response.json()
	except ValueError:
		logger.error(
			"Carrum referral reject invalid JSON status=%s",
			response.status_code,
		)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral portal"),
			"response": (response.text or "")[:2000] or None,
		}

	if isinstance(data, dict):
		payload_out = data.get("data", data)
	else:
		payload_out = data

	return {
		"success": True,
		"status_code": response.status_code,
		"data": payload_out,
		"message": _("Referral request rejected"),
	}


def get_referral_scheme_list_from_portal(role_id=None, hub_id=None, base_url=None, token=None):
	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	params = {}
	if role_id is not None and str(role_id).strip():
		params["roleId"] = str(role_id).strip()
	if hub_id is not None and str(hub_id).strip():
		params["hubId"] = str(hub_id).strip()
	return client.request(
		method="GET",
		path="/api/v1/referral-rewards/configs/active",
		params=params,
		log_tag="referral-config-list",
	)


def get_vendor_referral_configs_from_portal(agent_id=None, base_url=None, token=None):
	agent_key = (str(agent_id).strip() if agent_id is not None else "") or ""
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id is required"),
			"request_url": None,
		}

	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="GET",
		path="/api/v1/referral-rewards/configs/vendor",
		params={"agentId": agent_key},
		log_tag="vendor-referral-config-list",
	)


def create_vendor_referral_config_on_portal(
	agent_id=None,
	referral_milestones=None,
	is_active=True,
	base_url=None,
	token=None,
):
	agent_key = (str(agent_id).strip() if agent_id is not None else "") or ""
	if not agent_key:
		return {
			"success": False,
			"error": _("Agent id is required"),
			"request_url": None,
		}

	payload = {
		"agentId": agent_key,
		"referralMilestones": referral_milestones or [],
		"isActive": bool(is_active),
	}
	client = CarrumHttpClient(base_url=base_url, token=token, timeout=30)
	return client.request(
		method="POST",
		path="/api/v1/referral-rewards/configs/vendor",
		json=payload,
		log_tag="vendor-referral-config-create",
	)
