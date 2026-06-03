from datetime import datetime, timedelta, timezone
import json
import logging
import core.constants.enums as EnumValues
from frappe.utils.data import flt
from core.services import logged_requests as requests

from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
from frappe import _, logger

logger = frappe.logger("core.api.carrum_payment")
logger.setLevel(logging.INFO)

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))

def _resolve_lead_for_carrum_user_id(user_id):
    """Return CRM Lead name for ``custom_account_id`` / Carrum ``userId``, or None."""
    if not user_id:
        return None
    return frappe.db.get_value(
        "CRM Lead", {"custom_account_id": user_id}, "name"
    )


def _fetch_crm_lead_status_primary_secondary(filters):
    """Return ``(custom_primary_status, lead_status)`` from **CRM Lead Status** or ``None``."""
    return frappe.db.get_value(
        "CRM Lead Status",
        filters,
        ["custom_primary_status", "lead_status"],
    )


def _lead_matches_crm_status_row(lead, row):
    if not row:
        return False
    primary, secondary = row
    return (lead.primary_status or "") == (primary or "") and (
        lead.secondary_status or ""
    ) == (secondary or "")


def _lead_status_row_is_onboarding_drop(lead):
    """True when the lead's linked **CRM Lead Status** has ``is_onboarding_drop``."""
    pk = (getattr(lead, "status", None) or "").strip()
    if not pk or not frappe.db.exists("CRM Lead Status", pk):
        return False
    return bool(
        frappe.db.get_value("CRM Lead Status", pk, "is_onboarding_drop")
    )


def _lead_eligible_for_wallet_driver_stage(lead, driver_row, *, force=False):
    """
    Payment milestones (driver creation → PSD → FSD) apply when the lead is on the
    configured **driver creation** CRM Lead Status row, or when the lead is still in
    an **open** primary bucket (not ``Drop`` / ``Converted``).

    **Onboarding drop** (``Drop`` + linked status ``is_onboarding_drop``) is also
    eligible: those leads should still move to PSD/FSD when wallet milestones clear.

    Open-bucket leads often do not match ``driver_row`` (that row typically lives under
    ``Converted``), so wallet-based progression would never run without this branch.
    """
    if driver_row and _lead_matches_crm_status_row(lead, driver_row):
        return True
    p = (getattr(lead, "primary_status", None) or "").strip()
    if p == "Drop" and _lead_status_row_is_onboarding_drop(lead):
        return True
    if not p:
        return False
    if p in ("Drop", "Converted") and not force:
        return False
    return True


def _apply_crm_lead_status_row(lead, row, *, milestone=None):
    """Apply CRM Lead Status row via ``set`` + ``save`` (runs validations / hooks)."""
    primary, secondary = row
    from crm.fcrm.doctype.crm_lead.crm_lead import (
        get_crm_lead_status_name_for_primary_secondary,
    )

    lead.set("primary_status", primary)
    lead.set("secondary_status", secondary)
    pk = get_crm_lead_status_name_for_primary_secondary(primary, secondary)
    if pk:
        lead.set("status", pk)

    now = frappe.utils.now_datetime()
    if milestone == "psd":
        lead.set("psd_received_at", now)
    elif milestone == "fsd":
        lead.set("fsd_received_at", now)

    lead.save(ignore_permissions=True)

def _wallet_data_for_lead_account(account_id, *, wallet_data=None):
    """``walletData`` from legacy Carrum portal (hubFee / securityDeposit ``remaining``)."""
    if wallet_data is not None:
        return wallet_data if isinstance(wallet_data, dict) else None

    aid = (account_id or "").strip()
    if not aid:
        return None

    lead_name = frappe.db.get_value(
        "CRM Lead", {"custom_account_id": aid}, "name"
    )
    if not lead_name:
        return None

    try:
        from core.api.carrum_drivers import (
            _extract_portal_driver_results,
            _fetch_portal_driver_detail_http,
        )

        ok, payload, _skipped = _fetch_portal_driver_detail_http(lead_name)
        if not ok or not payload:
            return None
        results = _extract_portal_driver_results(payload)
    except Exception:
        frappe.logger().exception(
            "webhook_capture: portal driver detail failed for account_id=%s lead=%s",
            aid,
            lead_name,
        )
        return None

    if not isinstance(results, dict):
        return None
    wd = results.get("walletData")
    return wd if isinstance(wd, dict) else None


def maybe_update_lead_status_after_payment_capture(lead, wallet_data=None, force=False):
    """
    After a captured payment, optionally update CRM Lead ``primary_status`` /
    ``secondary_status`` using Carrum wallet balances (same source as the payment summary UI).

    Enforced progression is strictly forward-only:
    1) ``is_apply_on_driver_creation``
    2) ``is_apply_on_psd_conversion`` (hub fee fully paid)
    3) ``is_apply_on_fsd_conversion`` (full security deposit paid)
    4) ``is_apply_on_vehicle_assignment``

    This payment hook only progresses within payment stages (1 -> 2 -> 3).
    It never moves backward, and it never changes a lead already at stage 4.

    Stage-1 eligibility includes leads in an **open** primary bucket (not ``Drop`` /
    ``Converted``) even when their secondary does not yet match the driver-creation row,
    and leads on **onboarding drop** (``Drop`` + ``CRM Lead Status.is_onboarding_drop``).
    Pass ``force=True`` to also allow ``Drop`` / ``Converted`` primary buckets through
    the same wallet-based progression.

    If portal wallet data cannot be loaded, status is left unchanged.
    """
    account_id = (getattr(lead, "custom_account_id", None) or "").strip()
    if not account_id:
        return

    wallet = _wallet_data_for_lead_account(account_id, wallet_data=wallet_data)
    if not wallet:
        return

    hub_fee = wallet.get("hubFee") or {}
    sec_dep = wallet.get("securityDeposit") or {}
    hub_rem = flt(hub_fee.get("remaining"))
    sd_rem = flt(sec_dep.get("remaining"))

    driver_row = _fetch_crm_lead_status_primary_secondary(
        {"is_apply_on_driver_creation": 1}
    )
    fsd_row = _fetch_crm_lead_status_primary_secondary(
        {"is_apply_on_fsd_conversion": 1}
    )
    psd_row = _fetch_crm_lead_status_primary_secondary(
        {"is_apply_on_psd_conversion": 1}
    )
    va_row = _fetch_crm_lead_status_primary_secondary(
        {"is_apply_on_vehicle_assignment": 1}
    )

    # Never modify from the terminal stage in this flow.
    if va_row and _lead_matches_crm_status_row(lead, va_row):
        return

    is_hub_fee_cleared = hub_rem <= 0
    is_security_deposit_cleared = sd_rem <= 0

    # Stage 3: already at full SD conversion. Keep as-is (stage 4 comes from vehicle assignment).
    if fsd_row and _lead_matches_crm_status_row(lead, fsd_row):
        return

    # Stage 2 -> 3
    if (
        psd_row
        and _lead_matches_crm_status_row(lead, psd_row)
        and fsd_row
        and is_security_deposit_cleared
    ):
        _apply_crm_lead_status_row(lead, fsd_row, milestone="fsd")
        return

    # Stage 1 -> 2 or 1 -> 3 (if both dues are already cleared)
    if (
        driver_row
        and _lead_eligible_for_wallet_driver_stage(lead, driver_row, force=force)
        and fsd_row
        and is_hub_fee_cleared
        and is_security_deposit_cleared
    ):
        _apply_crm_lead_status_row(lead, fsd_row, milestone="fsd")
        return

    if (
        driver_row
        and _lead_eligible_for_wallet_driver_stage(lead, driver_row, force=force)
        and psd_row
        and is_hub_fee_cleared
    ):
        _apply_crm_lead_status_row(lead, psd_row, milestone="psd")


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

    lead = frappe.get_doc("CRM Lead", lead_id)
    phone_number = lead.mobile_no

    if not phone_number or not str(phone_number).strip():
        frappe.throw(_("Set mobile number on the lead before sending a payment link"))

    lead_name = lead.lead_name
    hub_fee = lead.hub_fee
    source = lead.source
    if not lead_name or not str(lead_name).strip():
        frappe.throw(_("Lead name is required before sending a payment link"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    hub_id = lead.hub_id
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None

    account_id = frappe.conf.get("carrum_account_id")
    source = source or "crm_payment_link"
    if hub_fee in (None, ""):
        frappe.throw(_("Hub fee is required"))

    payload = {
        "phoneNumber": str(phone_number).strip(),
        "displayId": lead_id,
        "leadName": lead_name or "",
        "hubFee": hub_fee,
        "hubId": hub_id,
        "amount": amount,
        "tag_type": tag_type,
        "source": source,
        "accountCreatorId": carrum_user_id,
    }
    if account_id is not None:
        payload["accountId"] = account_id

    headers = {"Authorization": token, "Content-Type": "application/json"}
    print(url)
    print(headers)
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        frappe.throw(_("Could not reach payment service: {0}").format(str(e)))
    
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
    hub_id = lead.hub_id

    phone_number = lead.mobile_no
    lead_name = lead.lead_name
    hub_fee = lead.hub_fee
    lead_account_id = lead.custom_account_id
    source = lead.source or "crm_other_payment"

    if hub_fee in (None, ""):
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


def _add_cash_execute(leadId=None, amount=None, paymentType=None, imageUrls=None):
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

    if hub_fee in (None, ""):
        frappe.throw(_("Hub fee is required payment"))

    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    hub_id = lead.hub_id
    carrum_user_id = carrum_user.get("id") if carrum_user is not None else None
    source = lead.source or "crm_cash_payment"
    out = {
        "phoneNumber": phone_number,
        "displayId": lead_id,
        "leadName": lead_name,
        "hubFee": hub_fee,
        "hubId": hub_id,
        "amount": amount_val,
        "tag_type": tag_type,
        "weekType": "currentWeek",
        "s3Links": s3_links,
        "accountCreatorId": carrum_user_id,
        "source": source,
    }

    if custom_account_id is not None:
        out["accountId"] = custom_account_id

    old_token = frappe.conf.get("old_carrum_token")
    old_carrum_base_url = frappe.conf.get("old_carrum_base_url")

    url = f"{str(old_carrum_base_url).rstrip('/')}/api/v1/payment/add_cash_for_crm"
    headers = {"Authorization": old_token, "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=out, headers=headers, timeout=60)
    except requests.RequestException:
        frappe.log_error(
            frappe.get_traceback(),
            f"add_cash: HTTP request failed (lead_id={lead_id}, url={url})",
        )
        frappe.throw(
            _("Could not reach payment service. Please try again or contact support.")
        )

    if not response.ok:
        snippet = (response.text or "")[:8000]
        frappe.log_error(
            f"lead_id={lead_id}\nHTTP {response.status_code}\n{snippet}",
            "add_cash: payment service non-OK response",
        )

    try:
        data = response.json()
    except ValueError:
        snippet = (response.text or "")[:8000]
        frappe.log_error(
            f"lead_id={lead_id}\n{snippet}",
            "add_cash: invalid JSON from payment service",
        )
        frappe.throw(_("Invalid JSON from payment service"))

    if data.get("status") != "success":
        msg = data.get("message") or data.get("errors") or _("Failed to add cash")
        try:
            payload_log = json.dumps(data, default=str)[:8000]
        except Exception:
            payload_log = str(data)
        frappe.log_error(
            f"lead_id={lead_id}\n{payload_log}",
            "add_cash: payment API returned failure",
        )
        return {
            "is_valid": False,
            "reason": msg,
        }

    return {"message": "success"}


@frappe.whitelist()
def add_cash(leadId=None, amount=None, paymentType=None, imageUrls=None):
    try:
        return _add_cash_execute(leadId, amount, paymentType, imageUrls)
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "add_cash: unexpected error")
        raise

@frappe.whitelist()
def webhook_capture():
    """
    Payment webhook. The HTTP body must be **valid JSON** (Frappe parses it before this runs).
    """

    d = frappe.request.get_json()
    if not d or not isinstance(d, dict):
        frappe.throw(_("Expected JSON body"), title=_("Payment webhook"))

    user_id = d.get("userId")
    _raw_tid = d.get("transactionId")
    transactionId = str(_raw_tid).strip() if _raw_tid is not None else ""

    if not user_id:
        frappe.throw(_("userId is required"), title=_("Payment webhook"))
    if not transactionId:
        frappe.throw(_("transactionId is required"), title=_("Payment webhook"))

    if frappe.db.exists("payment_logs", transactionId):
        return {
            "message": "already captured",
            "payment_log_id": transactionId,
        }

    lead_name = _resolve_lead_for_carrum_user_id(user_id)
    if not lead_name:
        frappe.throw(
            _("Lead not found for user_id: {0}").format(user_id),
            title=_("Payment webhook"),
        )
    lead = frappe.get_doc("CRM Lead", lead_name)
    lead_id = lead.name
    maybe_update_lead_status_after_payment_capture(lead)
    
    return {
        "message": "ok",
        "lead_id": lead_id,
    }

@frappe.whitelist()
def webhook_failed():
    """Failed payment webhook; ``transactionDate`` is UTC (naive or ISO-Z). Stored as IST."""
    # d = frappe.request.get_json()
    # if not d or not isinstance(d, dict):
    #     frappe.throw(_("Expected JSON body"), title=_("Payment webhook"))

    # amount = d.get("amount")
    # utr = d.get("utrNumber")
    # transactionDt = d.get("transactionDate")
    # user_id = d.get("userId")
    # _raw_tid = d.get("transactionId")
    # transactionId = str(_raw_tid).strip() if _raw_tid is not None else ""
    # imageUrls = d.get("imageUrls")
    # status = (d.get("status") or "").strip().lower()
    # statusMap = {
    #     "reject": "Rejected",
    #     "rejected": "Rejected",
    #     "rejet": "Rejected",
    #     "transferred": "Transferred",
    # }
    # finalStatus = statusMap.get(status, "Failed")
    # if not user_id:
    #     frappe.throw(_("userId is required"), title=_("Payment webhook"))
    # if not transactionId:
    #     frappe.throw(_("transactionId is required"), title=_("Payment webhook"))

    # transaction_date = _parse_transaction_timestamp_utc_to_naive_ist(transactionDt)

    # if frappe.db.exists("payment_logs", transactionId):
    #     return {
    #         "message": "already consumed",
    #         "payment_log_id": transactionId,
    #     }

    # lead_id = _resolve_lead_for_carrum_user_id(user_id)
    # if not lead_id:
    #     frappe.throw(
    #         _("Lead not found for user_id: {0}").format(user_id),
    #         title=_("Payment webhook"),
    #     )

    # paymentTag = d.get("paymentTag") or {}
    # hubFeeTag = flt(paymentTag.get("hubFeeTag"))
    # sdTag = flt(paymentTag.get("sdTag"))
    # settlementTag = flt(paymentTag.get("settlementTag"))
    # interestTag = flt(paymentTag.get("interestTag"))

    # sdBreakupAmount = hubFeeTag + sdTag
    # settlementBreakupAmount = settlementTag + interestTag

    # raw_plain = json.loads(frappe.as_json(d))

    # image_csv = _payment_log_image_csv_from_payload(imageUrls)

    # pl_kwargs = {
    #     "doctype": "payment_logs",
    #     "__newname": transactionId,
    #     "amount": amount,
    #     "lead": lead_id,
    #     "raw": raw_plain,
    #     "utr": utr,
    #     "sd_breakup_amount": sdBreakupAmount,
    #     "settlement_breakup_amount": settlementBreakupAmount,
    #     "transaction_date": transaction_date,
    #     "status": finalStatus,
    # }
    # if image_csv:
    #     pl_kwargs["image"] = image_csv
    # frappe.get_doc(pl_kwargs).save()

    return {
        "message": "ok",
    # "lead_id": lead_id,
    }