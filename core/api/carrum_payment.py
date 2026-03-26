import json

import frappe
from frappe.utils import get_datetime


def _log_payload(label, payload):
    frappe.logger().info("%s payload: %s", label, json.dumps(payload, default=str))


@frappe.whitelist()
def send_payment_link(lead_id: str,amount:float, type: str):
    """Send standard (online) payment link for a CRM Lead or CRM Deal."""
    frappe.get_doc("CRM Lead", lead_id)
    payload = {
        "lead_id": lead_id,
        "amount": amount,   
        "type": type,
    }
    _log_payload("send_payment_link", payload)
    return {"message": "success"}


@frappe.whitelist()
def send_other_payment_link(
    amount=None,
    utr=None,
    payment_type=None,
    image_url=None,
    lead_id=None,
):
    """Send / record other-mode payment flow (e.g. offline / manual)."""
    frappe.get_doc("CRM Lead", lead_id)
    payload = {
        "lead_id": lead_id,
        "amount": amount,
        "utr": utr,
        "payment_type": payment_type,
        "image_url": image_url,
    }
    _log_payload("send_other_payment_link", payload)
    return {"message": "success"}

@frappe.whitelist()
def webhook():
    """
    Payment webhook. The HTTP body must be **valid JSON** (Frappe parses it before this runs).

    Send `Content-Type: application/json` and a body like:
    {
      "status": "paid",
      "lead_id": "CRM-LEAD-00001",
      "amount": 100.5,
      "utr": "ABC123",
      "payment_type": "SD",
      "dt": "2025-03-25T12:00:00"
    }

    CamelCase keys from providers are also accepted: leadId, paymentType.
    `dt` must be a string (ISO 8601), not a bare datetime token (invalid JSON).
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