from urllib.parse import quote, urlencode

import requests

import frappe
from frappe import _

logger = frappe.logger("core::carrum_referral")


def create_lead_referral_on_portal(refereeId, referrerId, agentReferrerId, hubId):
	"""
	POST ``/api/v1/referral-rewards`` when both referee and referrer CRM leads are known.

	Payload includes ``refereeId``, ``referrerId``, ``agentReferrerId``, and ``hubId``.
	``referrerId`` / ``hubId`` may be None (sent as JSON null).

	Returns:
		dict with ``success`` bool; on success ``status_code`` and ``data`` (parsed JSON);
		on failure ``error`` and optionally ``status_code``, ``response``.
	"""
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

	url = f"{base_url}/api/v1/referral-rewards"
	payload = {
		"refereeId": refereeId,
		"referrerId": referrerId,
		"agentReferrerId": agentReferrerId,
		"hubId": hubId,
	}

	headers = {
		"Content-Type": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.post(url, json=payload, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum lead referral-rewards timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral portal timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum lead referral-rewards connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral portal"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum lead referral-rewards request error: %s", err)
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
			"Carrum lead referral-rewards HTTP error status=%s body=%s",
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
		logger.error(
			"Carrum lead referral-rewards invalid JSON status=%s",
			response.status_code,
		)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral portal"),
			"response": (response.text or "")[:2000] or None,
		}

	return {
		"success": True,
		"status_code": response.status_code,
		"data": data,
	}


def create_referral_on_portal(refereeId, agentReferrerId, hubId):
	"""
	Create a referral on the Carrum portal (POST ``/api/v1/referral-rewards``).

	Args:
		refereeId: Referee identifier (e.g. CRM Lead name or Carrum account id).
		agentReferrerId: Carrum user UUID for the referring agent.
		hubId: Default hub UUID from Carrum (optional if API allows).

	Returns:
		dict with ``success`` bool; on success includes ``status_code`` and ``data`` (parsed JSON);
		on failure includes ``error`` and optionally ``status_code``, ``response``.
	"""
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

	url = f"{base_url}/api/v1/referral-rewards"
	payload = {
		"refereeId": refereeId,
		"agentReferrerId": agentReferrerId,
		"hubId": hubId,
	}

	headers = {
		"Content-Type": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.post(url, json=payload, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referral-rewards timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral portal timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referral-rewards connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral portal"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referral-rewards request error: %s", err)
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
			"Carrum referral-rewards HTTP error status=%s body=%s",
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
		logger.error("Carrum referral-rewards invalid JSON status=%s", response.status_code)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral portal"),
			"response": (response.text or "")[:2000] or None,
		}

	return {
		"success": True,
		"status_code": response.status_code,
		"data": data,
	}


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

	referrer_segment = quote(referrer_id, safe="")
	url = f"{base_url}/api/v1/referral-rewards/referrer/{referrer_segment}"

	headers = {
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referrer referrals timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral service timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referrer referrals connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral service"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referrer referrals request error: %s", err)
		return {
			"success": False,
			"error": _("Referral list request failed: {0}").format(str(err)),
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
			"Carrum referrer referrals HTTP error status=%s body=%s",
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
		logger.error(
			"Carrum referrer referrals invalid JSON status=%s",
			response.status_code,
		)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral service"),
			"response": (response.text or "")[:2000] or None,
		}

	if isinstance(data, list):
		payload = data
	elif isinstance(data, dict):
		payload = data.get("data", data)
	else:
		payload = data

	return {
		"success": True,
		"status_code": response.status_code,
		"data": payload,
	}


def get_dm_referral_list(
	agent_referrer_id,
	page=1,
	limit=20,
	reward_type="AGENT_REFERRAL",
):
	"""
	GET referee summary list for an agent (DM / referral list).

	URL: ``{carrum_base_url}/agent/{agent_referrer_id}/referee-summary``
	Query: ``rewardType``, ``page``, ``limit`` (default ``AGENT_REFERRAL``, ``1``, ``20``).

	Returns:
		Same shape as ``create_referral_on_portal``: ``success``, optional ``data`` (parsed JSON),
		``status_code``, or ``error`` / ``response`` on failure.
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

	query = urlencode(
		{
			"rewardType": reward_type,
			"page": page,
			"limit": limit,
		}
	)
	url = f"{base_url}/api/v1/referral-rewards/agent/{agent_referrer_id}/referee-summary?{query}"

	headers = {
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referee-summary timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral list timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referee-summary connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral service"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referee-summary request error: %s", err)
		return {
			"success": False,
			"error": _("Referral list request failed: {0}").format(str(err)),
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
			"Carrum referee-summary HTTP error status=%s body=%s",
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
		logger.error("Carrum referee-summary invalid JSON status=%s", response.status_code)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral service"),
			"response": (response.text or "")[:2000] or None,
		}

	return {
		"success": True,
		"status_code": response.status_code,
		"data": data.get("data", {}),
	}


def get_lead_referred_by_details_from_portal(lead_id):
	"""
	GET referee referral details from Carrum (referrer context for a referee lead).

	URL: ``{carrum_base_url}/api/v1/referral-rewards/referee/{lead_id}``

	``lead_id`` is the path segment Carrum expects (typically CRM Lead name or account id).

	Returns:
		dict with ``success``, ``status_code``, ``data`` (parsed payload or nested ``data``),
		or ``error`` / ``response`` on failure.
	"""
	lead_id = (lead_id or "").strip()
	if not lead_id:
		return {
			"success": False,
			"error": _("Lead id is required"),
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

	lead_segment = quote(lead_id, safe="")
	url = f"{base_url}/api/v1/referral-rewards/referee/{lead_segment}"

	headers = {
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum referee detail timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to referral service timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum referee detail connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral service"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum referee detail request error: %s", err)
		return {
			"success": False,
			"error": _("Referral detail request failed: {0}").format(str(err)),
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
			"Carrum referee detail HTTP error status=%s body=%s",
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
		logger.error("Carrum referee detail invalid JSON status=%s", response.status_code)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral service"),
			"response": (response.text or "")[:2000] or None,
		}

	if isinstance(data, dict):
		payload = data.get("data", data)
	else:
		payload = data

	return {
		"success": True,
		"status_code": response.status_code,
		"data": payload,
	}


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
	user_name=None,
	reward_type="AGENT_REFERRAL",
):
	"""
	GET cumulative referral list from Carrum.

	URL: ``{carrum_base_url}/api/v1/referral-rewards/hub-summary?userName={{user_name}}&rewardType=AGENT_REFERRAL&page=1&limit=20``
	Query: ``page``, ``limit``.
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

	query = urlencode(
		{
			"userName": user_name,
			"rewardType": reward_type,
			"page": page,
			"limit": limit,
		}
	)
	url = f"{base_url}/api/v1/referral-rewards/hub-summary?{query}"

	headers = {
		"Accept": "application/json",
		"Authorization": token,
	}

	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.Timeout:
		logger.error("Carrum hub-summary timeout url=%s", url)
		return {
			"success": False,
			"error": _("Request to cumulative referral list timed out"),
		}
	except requests.exceptions.ConnectionError as err:
		logger.error("Carrum hub-summary connection error: %s", err)
		return {
			"success": False,
			"error": _("Could not connect to referral service"),
		}
	except requests.exceptions.RequestException as err:
		logger.error("Carrum hub-summary request error: %s", err)
		return {
			"success": False,
			"error": _("Cumulative referral list request failed: {0}").format(str(err)),
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
			"Carrum hub-summary HTTP error status=%s body=%s",
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
		logger.error("Carrum hub-summary invalid JSON status=%s", response.status_code)
		return {
			"success": False,
			"status_code": response.status_code,
			"error": _("Invalid JSON response from referral service"),
			"response": (response.text or "")[:2000] or None,
		}

	if isinstance(data, dict):
		payload = data.get("data", data)
	else:
		payload = data

	return {
		"success": True,
		"status_code": response.status_code,
		"data": payload,
	}
