import json

import requests as re

import frappe
from frappe import _

logger = frappe.logger("core::carrum_drivers")

old_carrum_base_url = frappe.conf.get("old_carrum_base_url")
old_carrum_token = frappe.conf.get("old_carrum_token")

@frappe.whitelist()
def get_driver_agreements(account_id: str) -> dict:
    """
    Fetch driver agreement history from Carrum (GET /api/v1/drivers/agreements).

    :param account_id: Carrum driver account identifier (query param account_id).
    """

    base = frappe.conf.get("old_carrum_base_url")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old carrum token is not configured (carrum_token)"))

    url = f"{base}/v1/driver/aggrementHistory/bydriverWise"
    params = {"account_id": account_id}
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
def send_agreement(lead_id: str):
    url = f"{old_carrum_base_url}/api/v1/driver/sendAgreementForDriver"

    payload = json.dumps({
    "accountId": "b1925efc-5404-48bf-af3f-8c477dd41c32",
    "driver_phone": "8287842425",
    "driver_name": "Kapil Rohilla",
    "driver_current_address": "House No 45, Sector 12, Hisar, Haryana",
    "aadhar_number": "926931798689",
    "pan_card": "ABCPK1234Q",
    "dl_number": "HR20 20210012345",
    "dl_issue_date": "2018-06-15",
    "dl_expiry_date": "2038-06-14",
    "driver_email": "ravi.kumar92@example.com",
    "driver_bank_account_number": "345678901234",
    "driver_small_id": "DRV10234",
    "schemeId": "9735ca8e-840f-4433-8fb6-8547daacd4fc",
    "bank_ifsc_code": "SBIN0001234",
    "Witness1": "Suresh Kumar",
    "Witness2": "Mahesh Transport Co.",
    "Witness3": "Ram Prasad",
    "Witness4": "Raghubir Singh",
    "hubId": "779db382-859d-48ee-ba17-d90ffa91cf24"
    })
    headers = {
    'Authorization': 'carrum eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZGVudGl0eUlkIjoiOThkMDU0YzgtNWY1Zi00ZDBkLTg4ZmMtZjNkNzQ2ZmM1MzRmIiwidG9rZW5UeXBlIjoiYWNjZXNzIiwidG9rZW5WZXJzaW9uIjo1NCwiaWQiOiJhM2VjYzgzYy1hMDBhLTRjMmUtYTY2Mi1mZmE5NzZhZDE3NDYiLCJyb2xlSWQiOiJjZjcwY2QxMS0wZDU1LTRiNWYtYjFmMC0yYzQ2ZGVmNGVjZjYiLCJodWJJZCI6Ijc3OWRiMzgyLTg1OWQtNDhlZS1iYTE3LWQ5MGZmYTkxY2YyNCIsImlhdCI6MTc3NTU0NjUwNCwiZXhwIjoxNzc1NjMyOTA0fQ.ZKbjXV8OQf0jKUQbU9Ou33pARca_gPsx1-VcYS6h1fQ',
    'Content-Type': 'application/json',
    'Cookie': 'full_name=Guest; sid=Guest; system_user=no; user_id=Guest; user_image='
    }

    response = re.post(url=url, headers=headers, json=payload)

    print(response.text)

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

@frappe.whitelist(methods=["POST"])
def lead_creation_webhook():
    """
    Carrum webhook: JSON body ``mobile_no``, ``displayId`` (CRM Lead ``name``, AAAA0001–ZZZZ9999),
    and optional ``source``.

    Creates a lead with **exactly** ``displayId`` as the document name (via ``insert(set_name=…)`` —
    required because Frappe otherwise clears ``name`` for naming_series autoname).

    If a CRM Lead with that ``name`` already exists, raises **DuplicateEntryError**.
    """
    from crm.fcrm.doctype.crm_lead.crm_lead import LEAD_ID_PATTERN
    from crm.utils import parse_phone_number

    data = frappe.request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    raw_display = data.get("displayId")
    displayId = str(raw_display).strip().upper() if raw_display is not None else ""
    phone_raw = data.get("mobile_no") or data.get("phoneNo") or data.get("phone")
    phoneNo = str(phone_raw).strip() if phone_raw is not None else ""

    source = data.get("source")
    if source is not None and isinstance(source, str):
        source = source.strip()

    if not displayId:
        frappe.throw(_("displayId is required"), frappe.ValidationError)
    if not LEAD_ID_PATTERN.match(displayId):
        frappe.throw(
            _("displayId must be a lead ID like AAAA0001, got {0}").format(displayId),
            frappe.ValidationError,
        )
    if not phoneNo:
        frappe.throw(_("phone is required"), frappe.ValidationError)

    parsed = parse_phone_number(phoneNo)
    if parsed.get("success"):
        mobile_no = parsed.get("national_number") or phoneNo
    else:
        mobile_no = phoneNo
        logger.warning(
            "lead_creation_webhook: phone parse failed for %r: %s",
            phoneNo,
            parsed.get("error"),
        )

    if frappe.db.exists("CRM Lead", displayId):
        frappe.throw(
            _("CRM Lead {0} already exists").format(frappe.bold(displayId)),
            frappe.DuplicateEntryError,
        )

    status_rows = frappe.get_all(
        "CRM Lead Status",
        pluck="name",
        order_by="position asc, creation asc",
        limit=1,
    )
    default_status = status_rows[0] if status_rows else None
    if not default_status:
        frappe.throw(
            _("No CRM Lead Status is configured. Add one in CRM Lead Status."),
            frappe.ValidationError,
        )

    lead = frappe.new_doc("CRM Lead")
    lead.flags.skip_crm_lead_auto_id = True
    lead.mobile_no = mobile_no
    lead.status = default_status
    lead.lead_type = "DRIVER"
    lead.lead_name = None

    meta = frappe.get_meta("CRM Lead")
    if source and meta.get_field("source"):
        lead.set("source", source)

    lead.insert(set_name=displayId, ignore_permissions=True)

    logger.info("lead_creation_webhook: created CRM Lead %s", lead.name)
    return {"message": "ok", "name": lead.name, "created": True}