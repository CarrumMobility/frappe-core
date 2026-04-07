import json

import requests

from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
from frappe import _
from frappe.utils import get_datetime, flt

def _log_payload(label, payload):
    frappe.logger().info("%s payload: %s", label, json.dumps(payload, default=str))


def _resolve_payment_doc(doctype=None, name=None, lead_id=None):
    """Validate CRM Lead or CRM Deal exists; return (doctype, name)."""
    dt = doctype
    nm = name or lead_id
    if not nm:
        frappe.throw(_("Document name is required"))
    if not dt:
        dt = "CRM Lead"
    if dt not in ("CRM Lead", "CRM Deal"):
        frappe.throw(_("Unsupported doctype for payment"))
    frappe.get_doc(dt, nm)
    return dt, nm

@frappe.whitelist()
def send_payment_link(lead_id=None, amount=None, tag_type=None, leadId=None):
    """
    Generate Carrum/Razorpay payment link for a CRM Lead.
    Accepts lead_id or leadId, amount, tag_type or type (from JSON body).
    """
    lead_id = lead_id or leadId or frappe.form_dict.get("lead_id") or frappe.form_dict.get("leadId")
    if not lead_id:
        frappe.throw(_("Lead is required"))

    raw_amount = amount if amount is not None else frappe.form_dict.get("amount")
    if raw_amount is None or (isinstance(raw_amount, str) and not str(raw_amount).strip()):
        frappe.throw(_("Amount is required"))
    amount = flt(raw_amount)
    if amount <= 0:
        frappe.throw(_("Amount must be a positive number"))

    tag_type = (
        tag_type
        or frappe.form_dict.get("tag_type")
        or frappe.form_dict.get("type")
    )
    if tag_type is None or str(tag_type).strip() == "":
        frappe.throw(_("Payment type (tag_type) is required"))
    tag_norm = str(tag_type).strip()
    if tag_norm not in ("security_deposit", "settlement"):
        frappe.throw(_("Payment type must be security_deposit or settlement"))
    tag_type = tag_norm

    base = frappe.conf.get("old_carrum_base_url")
    if not base:
        frappe.throw(_("Carrum base URL is not configured (carrum_base_url)"))
    url = f"{str(base).rstrip('/')}/api/v1/payment/generatePaymentLinkForCRM"

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Carrum token is not configured (carrum_token)"))

    lead_val = frappe.db.get_value(
        "CRM Lead",
        lead_id,
        ["mobile_no", "lead_name", "hub_fee"],
    )
    if not lead_val:
        frappe.throw(_("CRM Lead not found"))

    phone_number, lead_name, hub_fee = lead_val
    if not phone_number or not str(phone_number).strip():
        frappe.throw(_("Set mobile number on the lead before sending a payment link"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None

    payload = {
        "phoneNumber": str(phone_number).strip(),
        "displayId": lead_id,
        "leadName": lead_name or "",
        "hubFee": hub_fee,
        "hubId": default_hub_id,
        "amount": amount,
        "tag_type": tag_type,
        "accountCreatorId": carrum_user_id,
    }

    print("==========sendPaymentLink==========")
    print(payload)
    
    headers = {"Authorization": token, "Content-Type": "application/json"}
    print(url)
    print(headers)
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        frappe.throw(_("Could not reach payment service: {0}").format(str(e)))
    print(response)
    print('==========sendPaymentLink==========')
    if response.status_code >= 400:
        body = (response.text or "")[:500]
        frappe.throw(
            _("Payment API error ({0}): {1}").format(response.status_code, body or response.reason)
        )

    try:
        data = response.json()
    except ValueError:
        frappe.throw(_("Invalid JSON from payment service"))

    if data.get("status") != "success":
        msg = data.get("message") or data.get("errors") or _("Payment link generation failed")
        frappe.throw(str(msg))

    results = data.get("results") or {}
    payment_link = results.get("payment_link")
    payment_qr = results.get("payment_qr_code_link")

    if not payment_link:
        frappe.throw(_("Payment service did not return a payment link"))

    return {
        "paymentLink": payment_link,
        "paymentQrCodeLink": payment_qr or "",
    }


def _payment_type_key(payment_type) -> str:
    """Map UI labels to compact type keys (e.g. webhook / integrations)."""
    s = (payment_type or "").strip()
    if not s:
        return ""
    if s in ("Security Deposit",) or "security" in s.lower():
        return "security"
    if s in ("Settlement",) or "settlement" in s.lower():
        return "settlement"
    return s.lower().replace(" ", "_")

@frappe.whitelist()
def send_other_payment_link(
    amount=None,
    utr=None,
    payment_type=None,
    image_url=None,
    lead_id=None,
    doctype=None,
    name=None,
    mode=None,
):
    """Send / record other-mode payment (Other bank transfer, Cash with receipt, etc.)."""
    dt, nm = _resolve_payment_doc(
        doctype=doctype,
        name=name,
        lead_id=lead_id,
    )

    mode_norm = (mode or "").strip()
    if mode_norm.lower() == "cash":
        if not (image_url and str(image_url).strip()):
            frappe.throw(_("Attach a receipt for cash payment"))
        amount_val = flt(amount or 0)
    else:
        if not str(amount or "").strip() and not str(utr or "").strip():
            frappe.throw(_("Enter amount or UTR"))
        amount_val = flt(amount) if str(amount or "").strip() else None

    type_key = _payment_type_key(payment_type)

    payload = {
        "doctype": dt,
        "name": nm,
        "lead_id": nm if dt == "CRM Lead" else None,
        "deal_id": nm if dt == "CRM Deal" else None,
        "mode": mode_norm or "Other",
        "amount": amount_val,
        "utr": utr,
        "payment_type": payment_type,
        "type_key": type_key,
        "image_url": image_url,
    }
    _log_payload("send_other_payment_link", payload)
    return {"message": "success"}

@frappe.whitelist()
def webhook_capture():
    """
    Payment webhook. The HTTP body must be **valid JSON** (Frappe parses it before this runs).


    """

   
    d = frappe.form_dict

    status = d.get("status")
    lead_id = d.get("leadId")
    amount = d.get("amount")
    utr = d.get("utr")
    payment_type =d.get("paymentType")
    dt_raw = d.get("dt")
    user_id = d.get("user_id")

    payload = {
        "status": status,
        "lead_id": lead_id,
        "amount": amount,
        "utr": utr,
        "payment_type": payment_type,
        "dt": dt_raw,
        "user_id": user_id
    }
    print(payload)
    _log_payload("payment_webhook", payload)

    parsed_dt = None
    if dt_raw:
        try:
            parsed_dt = get_datetime(dt_raw)
        except Exception:
            frappe.logger().warning("payment_webhook: could not parse dt=%r", dt_raw)

    return {
        "message": "ok",
        "lead_id": lead_id,
        "parsed_dt": str(parsed_dt) if parsed_dt else None,
    }

@frappe.whitelist()
def webhook_failed():
    print("======webhook_failed")
    body = frappe.request.get_json()
    print(body)

    return {
        "status": "success",
    }