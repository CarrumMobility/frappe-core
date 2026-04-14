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
        ["mobile_no", "lead_name", "hub_fee",'custom_account_id'],
    )
    if not lead_val:
        frappe.throw(_("CRM Lead not found"))

    phone_number, lead_name, hub_fee ,custom_account_id= lead_val
    if not phone_number or not str(phone_number).strip():
        frappe.throw(_("Set mobile number on the lead before sending a payment link"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None

    account_id = frappe.conf.get("carrum_account_id")
    
    if not hub_fee:
        frappe.throw(_("Hub fee is required"))

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
    if account_id is not None:
        payload["accountId"] = account_id

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
            _("Payment Service Unavailable ({0}): {1}").format(response.status_code, body or response.reason)
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

def _normalize_payment_image_urls(image_url=None, image_urls=None):
    """Merge single URL and/or list into a deduped ordered list (primary first)."""
    out = []
    if image_urls is not None:
        raw = image_urls
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        raw = parsed
                    else:
                        raw = [s]
                except (ValueError, TypeError):
                    raw = [s]
        if isinstance(raw, (list, tuple)):
            for u in raw:
                t = str(u).strip()
                if t and t not in out:
                    out.append(t)
    if image_url and str(image_url).strip():
        u = str(image_url).strip()
        if u not in out:
            out.insert(0, u)
    return out


def _tag_type_for_carrum_api(payment_type) -> str:
    """Normalize UI label or key to security_deposit | settlement for Carrum payment APIs."""
    s = str(payment_type or "").strip()
    if not s:
        frappe.throw(_("Payment type is required"))
    low = s.lower()
    if s == "Security Deposit" or ("security" in low and "deposit" in low):
        return "security_deposit"
    if s == "Settlement" or "settlement" in low:
        return "settlement"
    if s in ("security_deposit", "settlement"):
        return s
    frappe.throw(_("Payment type must be security deposit or settlement"))


def _merge_request_body():
    body = {}
    if getattr(frappe, "request", None):
        try:
            body = frappe.request.get_json(silent=True) or {}
        except Exception:
            body = {}
    return body


@frappe.whitelist()
def add_other_payment(
    amount=None,
    utr=None,
    payment_type=None,
    image_url=None,
    image_urls=None,
    lead_id=None,
    doctype=None,
    name=None,
):
    """Record non-online payment (bank transfer / UTR, optional receipt images)."""
    dt, nm = _resolve_payment_doc(
        doctype=doctype,
        name=name,
        lead_id=lead_id,
    )

    body = _merge_request_body()
    if image_url is None:
        image_url = body.get("image_url")
    if image_urls is None:
        image_urls = body.get("image_urls")
    if amount is None:
        amount = body.get("amount")
    if utr is None:
        utr = body.get("utr")
    # if payment_type is None:
    payment_type = body.get("payment_type")
    payment_type_str = str(payment_type).strip().lower()
    if "security" in payment_type_str and "deposit" in payment_type_str:
        payment_type = "security_deposit"
    elif "settlement" in payment_type_str:
        payment_type = "settlement"
    else:
        frappe.throw(_("Invalid payment type"))

    print("===",payment_type)
    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None
    lead = frappe.get_doc("CRM Lead", lead_id)

    phone_number = lead.mobile_no
    lead_name = lead.lead_name
    hub_fee = lead.hub_fee
    hub_id = lead.hub_id
    lead_account_id = lead.custom_account_id

    if not str(amount or "").strip() and not str(utr or "").strip():
        frappe.throw(_("Enter amount or UTR"))

    payload = {
        "phoneNumber": str(phone_number).strip(),
        "displayId": lead_id,
        "leadName": lead_name,
        "hubFee": hub_fee,
        "hubId": hub_id,
        "amount": amount,
        "tag_type": str(payment_type).lower(),
        "s3Links": image_urls,
        "utr_number": utr,
        "accountCreatorId": carrum_user_id,
    }
    if lead_account_id is not None:
        payload['accountId'] = lead_account_id

    print("==========add_other_payment==========")
    print(payload)
    print("==========add_other_payment==========")
    
    old_carrum_base_url = frappe.conf.get("old_carrum_base_url")
    old_carrum_token = frappe.conf.get("old_carrum_token")
    headers = {"Authorization": old_carrum_token, "Content-Type": "application/json"}
    url = f"{old_carrum_base_url}/api/v1/payment/otherForCRM"

    response = requests.post(url,headers=headers, json=payload, timeout=60)
    print(response)

    try:
        data = response.json()
    except ValueError:
        return {
            "is_valid": False,
            "reason": _("Invalid JSON from payment service")
        }

    print(data)
    
    if data.get('status') != "success":
        message = data.get("message") or data.get("error") or _("Failed to add other payment")
        return {
            "is_valid": False,
            "reason": message
        }

    if response.ok != True:
        return {
            "is_valid": False,
            "reason": response.text
        }

    return {
        "is_valid": True,
        "reason": None,
        "data": data.get("results") or {}
    }


@frappe.whitelist()
def add_cash(leadId=None, amount=None, paymentType=None, imageUrls=None):
    body = _merge_request_body()
    lead_id = leadId or body.get("leadId") or body.get("lead_id")
    if not lead_id:
        frappe.throw(_("Lead is required"))

    raw_amount = amount if amount is not None else body.get("amount")
    if raw_amount is None or (isinstance(raw_amount, str) and not str(raw_amount).strip()):
        frappe.throw(_("Amount is required"))
    amount_val = flt(raw_amount)

    pt = paymentType if paymentType is not None else body.get("paymentType") or body.get("payment_type")
    tag_type = _tag_type_for_carrum_api(pt)

    imgs = imageUrls if imageUrls is not None else body.get("imageUrls") or body.get("image_urls")
    if not imgs:
        frappe.throw(_("Attach at least one receipt image"))
    if isinstance(imgs, str):
        try:
            imgs = json.loads(imgs)
        except (ValueError, TypeError):
            imgs = [imgs]
    if not isinstance(imgs, (list, tuple)):
        imgs = [imgs]
    s3_links = [str(u).strip() for u in imgs if str(u).strip()]
    if not s3_links:
        frappe.throw(_("Attach at least one receipt image"))

    lead = frappe.get_doc("CRM Lead", lead_id)

    lead_name = lead.lead_name
    phone_number = lead.mobile_no
    hub_fee = lead.hub_fee
    custom_account_id = lead.custom_account_id

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None

    out = {
        "phoneNumber": phone_number,
        "displayId": lead_id,
        "leadName": lead_name,
        "hubFee": hub_fee,
        "hubId": default_hub_id,
        "amount": amount_val,
        "tag_type": tag_type,
        "weekType": "currentWeek",
        "s3Links": s3_links,
        "accountCreatorId": carrum_user_id,
    }

    if custom_account_id is not None:
        out["accountId"] = custom_account_id

    old_token = frappe.conf.get("old_carrum_token")
    old_carrum_base_url = frappe.conf.get("old_carrum_base_url")

    url = f"{str(old_carrum_base_url).rstrip('/')}/api/v1/payment/add_cash_for_crm"
    headers = {"Authorization": old_token, "Content-Type": "application/json"}
    response = requests.post(url, json=out, headers=headers, timeout=60)
    
    try:
        data = response.json()
    except ValueError:
        frappe.throw(_("Invalid JSON from payment service"))

    if data.get("status") != "success":
        msg = data.get("message") or data.get("errors") or _("Failed to add cash")
        return {
            "is_valid": False,
            "reason": msg
        }

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