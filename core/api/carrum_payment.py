from datetime import datetime, timedelta, timezone
import json

from frappe.utils.data import flt
import requests

from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
from frappe import _

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))


def _parse_transaction_timestamp_utc_to_naive_ist(dt_raw):
    """
    Carrum webhooks send transaction time in UTC (ISO ending in Z, or naive UTC string).
    Normalize to a naive datetime in IST for ``payment_logs.transaction_date``.
    """
    from frappe.utils import now_datetime

    if dt_raw is None:
        return now_datetime()
    s = str(dt_raw).strip()
    if not s:
        return now_datetime()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        frappe.logger().warning(
            "payment_webhook: could not parse transactionDate=%r", dt_raw
        )
        return now_datetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST).replace(tzinfo=None)


def _resolve_lead_for_carrum_user_id(user_id):
    """Return CRM Lead name for ``custom_account_id`` / Carrum ``userId``, or None."""
    if not user_id:
        return None
    return frappe.db.get_value(
        "CRM Lead", {"custom_account_id": user_id}, "name"
    )


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
        ["mobile_no", "lead_name", "hub_fee",'custom_account_id', 'source'],
    )
    if not lead_val:
        frappe.throw(_("CRM Lead not found"))

    phone_number, lead_name, hub_fee, custom_account_id, source = lead_val
    if not lead_name or not str(lead_name).strip():
        frappe.throw(_("Lead name is required before sending a payment link"))
    if not phone_number or not str(phone_number).strip():
        frappe.throw(_("Set mobile number on the lead before sending a payment link"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None

    account_id = frappe.conf.get("carrum_account_id")
    source = source or "crm_payment_link"
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
        "source": source,
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

    body = _merge_request_body()
    if image_url is None:
        image_url = body.get("image_url")
    if image_urls is None:
        image_urls = body.get("image_urls")
    if amount is None:
        amount = body.get("amount")
    if utr is None:
        utr = body.get("utr")
    
    payment_type = body.get("payment_type")
    payment_type_str = str(payment_type).strip().lower()
    if "security" in payment_type_str and "deposit" in payment_type_str:
        payment_type = "security_deposit"
    elif "settlement" in payment_type_str:
        payment_type = "settlement"
    else:
        frappe.throw(_("Invalid payment type"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None
    lead = frappe.get_doc("CRM Lead", lead_id)

    phone_number = lead.mobile_no
    lead_name = lead.lead_name
    hub_fee = lead.hub_fee
    hub_id = lead.hub_id
    lead_account_id = lead.custom_account_id
    source = lead.source or "crm_other_payment"

    if not hub_fee:
        frappe.throw(_("Hub fee is required payment"))

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
        "source": source,
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
    s3_links = []
    if imgs:
        if isinstance(imgs, str):
            try:
                imgs = json.loads(imgs)
            except (ValueError, TypeError):
                imgs = [imgs]
        if not isinstance(imgs, (list, tuple)):
            imgs = [imgs]
        s3_links = [str(u).strip() for u in imgs if str(u).strip()]

    lead = frappe.get_doc("CRM Lead", lead_id)

    lead_name = lead.lead_name
    phone_number = lead.mobile_no
    hub_fee = lead.hub_fee
    custom_account_id = lead.custom_account_id

    if not hub_fee:
        frappe.throw(_("Hub fee is required payment"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None
    source = lead.source or "crm_cash_payment"
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
        "source":source 
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

    d = frappe.request.get_json()
    print("====================payment_capture============================")
    print(d)
    print("====================payment_capture============================")
    if not d or not isinstance(d, dict):
        frappe.throw(_("Expected JSON body"), title=_("Payment webhook"))

    amount = d.get("amount")
    utr = d.get("utrNumber")
    transactionDt = d.get("transactionDate")
    user_id = d.get("userId")
    _raw_tid = d.get("transactionId")
    transactionId = str(_raw_tid).strip() if _raw_tid is not None else ""
    imageUrls = d.get("imageUrls")

    if not user_id:
        frappe.throw(_("userId is required"), title=_("Payment webhook"))
    if not transactionId:
        frappe.throw(_("transactionId is required"), title=_("Payment webhook"))

    transaction_date = _parse_transaction_timestamp_utc_to_naive_ist(transactionDt)

    existing_log = frappe.db.get_value(
        "payment_logs", {"carrum_id": transactionId}, "name"
    )
    if existing_log:
        return {
            "message": "already captured",
            "payment_log_id": existing_log,
        }

    lead_name = _resolve_lead_for_carrum_user_id(user_id)
    if not lead_name:
        frappe.throw(
            _("Lead not found for user_id: {0}").format(user_id),
            title=_("Payment webhook"),
        )
    lead = frappe.get_doc("CRM Lead", lead_name)
    lead_id = lead.name
    lead.db_set(
        "total_paid_amount",
        flt(lead.total_paid_amount) + flt(amount),
    )

    paymentTag = d.get("paymentTag") or {}
    hubFeeTag = flt(paymentTag.get("hubFeeTag"))
    sdTag = flt(paymentTag.get("sdTag"))
    settlementTag = flt(paymentTag.get("settlementTag"))
    interestTag = flt(paymentTag.get("interestTag"))

    sdBreakupAmount = hubFeeTag + sdTag
    settlementBreakupAmount = settlementTag + interestTag

    raw_plain = json.loads(frappe.as_json(d))

    image_url = None
    if isinstance(imageUrls, list) and imageUrls:
        image_url = imageUrls[0] if isinstance(imageUrls[0], str) else None
    elif isinstance(imageUrls, str) and imageUrls.strip():
        image_url = imageUrls.strip()

    paymentLog = frappe.new_doc("payment_logs")
    paymentLog.set("amount", amount)
    paymentLog.set("carrum_id", transactionId)
    if image_url:
        paymentLog.set("image", image_url)
    paymentLog.set("lead", lead_id)
    paymentLog.set("raw", raw_plain)
    paymentLog.set("utr", utr)
    paymentLog.set("sd_breakup_amount", sdBreakupAmount)
    paymentLog.set("settlement_breakup_amount", settlementBreakupAmount)
    paymentLog.set("transaction_date", transaction_date)
    paymentLog.set("status", "Captured")
    paymentLog.save()

    return {
        "message": "ok",
        "lead_id": lead_id,
    }

@frappe.whitelist()
def webhook_failed():
    """Failed payment webhook; ``transactionDate`` is UTC (naive or ISO-Z). Stored as IST."""
    d = frappe.request.get_json()
    if not d or not isinstance(d, dict):
        frappe.throw(_("Expected JSON body"), title=_("Payment webhook"))

    amount = d.get("amount")
    utr = d.get("utrNumber")
    transactionDt = d.get("transactionDate")
    user_id = d.get("userId")
    _raw_tid = d.get("transactionId")
    transactionId = str(_raw_tid).strip() if _raw_tid is not None else ""
    imageUrls = d.get("imageUrls")

    if not user_id:
        frappe.throw(_("userId is required"), title=_("Payment webhook"))
    if not transactionId:
        frappe.throw(_("transactionId is required"), title=_("Payment webhook"))

    transaction_date = _parse_transaction_timestamp_utc_to_naive_ist(transactionDt)

    existing_log = frappe.db.get_value(
        "payment_logs", {"carrum_id": transactionId}, "name"
    )

    if existing_log:
        return {
            "message": "already saved",
            "payment_log_id": existing_log,
        }

    lead_id = _resolve_lead_for_carrum_user_id(user_id)
    if not lead_id:
        frappe.throw(
            _("Lead not found for user_id: {0}").format(user_id),
            title=_("Payment webhook"),
        )

    paymentTag = d.get("paymentTag") or {}
    hubFeeTag = flt(paymentTag.get("hubFeeTag"))
    sdTag = flt(paymentTag.get("sdTag"))
    settlementTag = flt(paymentTag.get("settlementTag"))
    interestTag = flt(paymentTag.get("interestTag"))

    sdBreakupAmount = hubFeeTag + sdTag
    settlementBreakupAmount = settlementTag + interestTag

    raw_plain = json.loads(frappe.as_json(d))

    image_url = None
    if isinstance(imageUrls, list) and imageUrls:
        image_url = imageUrls[0] if isinstance(imageUrls[0], str) else None
    elif isinstance(imageUrls, str) and imageUrls.strip():
        image_url = imageUrls.strip()

    paymentLog = frappe.new_doc("payment_logs")
    paymentLog.set("amount", amount)
    paymentLog.set("carrum_id", transactionId)
    if image_url:
        paymentLog.set("image", image_url)
    paymentLog.set("lead", lead_id)
    paymentLog.set("raw", raw_plain)
    paymentLog.set("utr", utr)
    paymentLog.set("sd_breakup_amount", sdBreakupAmount)
    paymentLog.set("settlement_breakup_amount", settlementBreakupAmount)
    paymentLog.set("transaction_date", transaction_date)
    paymentLog.set("status", "Failed")
    paymentLog.save()

    return {
        "message": "ok",
        "lead_id": lead_id,
    }