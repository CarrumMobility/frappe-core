import json

import requests as re

import frappe
from frappe import _

logger = frappe.logger("core::carrum_drivers")


@frappe.whitelist()
def get_driver_agreements(account_id: str) -> dict:
    """
    Fetch driver agreement history from Carrum (GET /api/v1/drivers/agreements).

    :param account_id: Carrum driver account identifier (query param account_id).
    """
    aid = (account_id or "").strip()
    if not aid:
        frappe.throw(_("Account ID is required"))

    base = frappe.conf.get("carrum_base_url")
    if not base:
        frappe.throw(_("Carrum base URL is not configured (carrum_base_url)"))

    token = frappe.conf.get("carrum_token")
    if not token:
        frappe.throw(_("Carrum token is not configured (carrum_token)"))

    url = f"{base}/v1/driver/aggrementHistory/bydriverWise"
    params = {"account_id": aid}
    headers = {"Authorization": token}

    try:
        response = re.get(url, params=params, headers=headers, timeout=60)
    except re.exceptions.RequestException as e:
        logger.exception("Carrum agreements request failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    try:
        body = response.json()
    except ValueError:
        logger.error(
            "Carrum agreements non-JSON response (HTTP %s): %s",
            response.status_code,
            (response.text or "")[:500],
        )
        frappe.throw(_("Invalid response from Carrum"))

    if not response.ok:
        logger.error(
            "Carrum agreements HTTP %s: %s",
            response.status_code,
            json.dumps(body, default=str)[:1000],
        )
        message = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error")
            err = body.get("errors")
            if isinstance(err, list) and err:
                message = message or err[0].get("message") if isinstance(err[0], dict) else str(err[0])
        frappe.throw(message or _("Carrum API error ({0})").format(response.status_code))

    return body

@frappe.whitelist()
def view_agreement(): 
    pass
    return "success"

@frappe.whitelist()
def download_agreement():
    pass
    return "success"

@frappe.whitelist()
def send_agreement():
    pass

@frappe.whitelist()
def upload_agreement():
    pass

@frappe.whitelist()
def get_portal_driver_detail(account_id: str | None = None):
    """
    Portal driver detail from legacy Carrum. Not stored on CRM Lead.

    :param account_id: Carrum driver account id (prefer CRM custom field, else Uber ID / hub id).
    """
    aid = (account_id or "").strip()
    if not aid:
        frappe.throw(_("Account ID is required (driver account, Uber ID, or Hub ID on the lead)."))

    base = frappe.conf.get("old_carrum_base_url")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    url = f"{base}/api/v1/driver/accounts/{aid}"
    print("======get_portal_driver_detail url: " + url)
    headers = {"Authorization": token}

    try:
        response = re.get(url, headers=headers)
    except re.exceptions.RequestException as e:
        logger.exception("get_portal_driver_detail request failed: %s", e)
        return {"success": False, "message": "Failed to get driver details"}
    print(response.text)
    if not response.ok:
        logger.error(
            "get_portal_driver_detail HTTP %s: %s",
            response.status_code,
            (response.text or "")[:500],
        )
        return {"success": False, "message": "Failed to get driver details"}

    try:
        data = response.json()
    except ValueError:
        logger.error(
            "get_portal_driver_detail non-JSON (HTTP %s): %s",
            response.status_code,
            (response.text or "")[:500],
        )
        return {"success": False}

    return {"success": True, "data": data}


@frappe.whitelist()
def update_driver(account_id: str, data: str | None = None):
    """
    Push driver scheme update to Carrum (legacy portal API).

    :param account_id: Carrum driver account id (CRM Lead Hub ID when aligned).
    :param data: JSON string with key ``scheme_id`` (required for PATCH).
    """
    aid = (account_id or "").strip()
    if not aid:
        frappe.throw(_("Account ID is required"))

    payload = {}
    if data:
        if isinstance(data, str):
            try:
                payload = json.loads(data) if data.strip() else {}
            except json.JSONDecodeError:
                frappe.throw(_("Invalid JSON in data"))
        elif isinstance(data, dict):
            payload = data

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    body = {}
    scheme_id = payload.get("scheme_id")
    if scheme_id is not None and scheme_id != "":
        if isinstance(scheme_id, (int, float)):
            body["scheme_id"] = int(scheme_id)
        else:
            s = str(scheme_id).strip()
            if s.isdigit():
                body["scheme_id"] = int(s)
            else:
                body["scheme_id"] = s

    if not body:
        return {"success": True}

    url = f"{base}/api/v1/driver/accounts/{aid}"
    headers = {"Authorization": token, "Content-Type": "application/json"}

    try:
        response = re.patch(url, headers=headers, json=body, timeout=60)
    except re.exceptions.RequestException as e:
        logger.exception("update_driver request failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    try:
        resp_body = response.json()
    except ValueError:
        resp_body = None

    if not response.ok:
        logger.error(
            "update_driver HTTP %s: %s",
            response.status_code,
            (response.text or "")[:1000],
        )
        message = None
        if isinstance(resp_body, dict):
            message = resp_body.get("message") or resp_body.get("error")
            err = resp_body.get("errors")
            if isinstance(err, list) and err:
                first = err[0]
                message = message or (
                    first.get("message") if isinstance(first, dict) else str(first)
                )
        frappe.throw(message or _("Carrum API error ({0})").format(response.status_code))

    return {"success": True, "data": resp_body}

@frappe.whitelist()
def lead_creation_webhook():
    print("======lead_creation_webhook")
    print(frappe.request.get_json())

    return {
        "message": "ok",
    }