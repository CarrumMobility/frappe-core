import base64
import json
from datetime import date, datetime
from uuid import UUID
from core.constants.enums import EnumValues
from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
from crm.api.api_errors import CrmApiErrors, throw_custom_api_error
from crm.fcrm.doctype.crm_lead.crm_lead import LEAD_ID_PATTERN, apply_default_crm_lead_status_to_doc
from core.services.util_service import util_service
from crm.utils import parse_phone_number
from core.services import logged_requests as re
import frappe
from frappe import _

from typing import Optional

from pydantic import BaseModel, ValidationError, field_validator

logger = frappe.logger("core.api.carrum_drivers")


class UpdateDriverDtoSchema(BaseModel):
    """Request body for ``update_driver`` (CRM frontend sends a JSON object, not a string)."""

    scheme_id: Optional[str | int] = None
    scheme_type: Optional[str] = None
    old_scheme_name: Optional[str] = None
    tenure: Optional[int] = None
    emi_id: Optional[str] = None
    remove_emi: Optional[bool] = None
    uber_id: Optional[UUID] = None

    @field_validator("scheme_type", "old_scheme_name", mode="before")
    @classmethod
    def _strip_str_field(cls, v):
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("tenure", mode="before")
    @classmethod
    def _validate_tenure(cls, v):
        if v is None or v == "":
            return None
        val = int(v)
        if val < 1 or val > 10:
            raise ValueError(_("Tenure must be between 1 and 10"))
        return val

    @field_validator("uber_id", mode="before")
    @classmethod
    def _normalize_uber_id(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, UUID):
            return v
        s = str(v).strip()
        if not s:
            return None
        try:
            return UUID(s)
        except ValueError:
            raise ValueError(_("Uber ID must be a valid UUID"))


def _date_to_json_value(val):
    """Coerce Date/datetime/str to YYYY-MM-DD (or None) for ``requests`` JSON bodies."""
    if val is None or val == "":
        return None
    if isinstance(val, str):
        s = val.strip()
        return s or None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val).strip() or None


def _lead_field_missing(val, *, attach: bool = False) -> bool:
    if attach:
        return not (val and str(val).strip())
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    return False


def _looks_like_portal_driver_results(o) -> bool:
    if not o or not isinstance(o, dict):
        return False
    markers = (
        "scheme_id",
        "uber_id",
        "chequeData",
        "scheme_alias_detail",
        "assignedVehicle",
        "walletData",
    )
    return any(k in o for k in markers)


def _extract_portal_driver_results(envelope_data) -> dict | None:
    """Normalize Carrum portal driver payload to the ``results`` object."""
    if envelope_data is None:
        return None
    top = envelope_data
    if isinstance(top, dict):
        if top.get("results") and isinstance(top["results"], dict):
            o = top["results"]
            if _looks_like_portal_driver_results(o):
                return o
        if isinstance(top.get("data"), dict) and isinstance(top["data"].get("results"), dict):
            o = top["data"]["results"]
            if _looks_like_portal_driver_results(o):
                return o
        msg = top.get("message")
        if isinstance(msg, dict):
            inner = msg.get("data") or msg
            if isinstance(inner, dict) and isinstance(inner.get("results"), dict):
                return inner["results"]
        if _looks_like_portal_driver_results(top):
            return top
        if isinstance(top.get("results"), dict):
            return top["results"]
    return None


def _portal_driver_has_scheme(account_id: str) -> bool:
    """True when ``get_portal_driver_detail`` includes an assigned scheme."""
    base = frappe.conf.get("old_carrum_base_url")
    token = frappe.conf.get("old_carrum_token")
    if not base or not token:
        return False
    aid = (account_id or "").strip()
    if not aid:
        return False
    url = f"{str(base).rstrip('/')}/api/v1/driver/accounts/{aid}"
    headers = {"Authorization": token}
    try:
        response = re.get(url, headers=headers, timeout=60)
    except re.exceptions.RequestException:
        return False
    if not response.ok:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    results = _extract_portal_driver_results(payload)
    if not results:
        return False
    if results.get("scheme_id") or results.get("schemeId"):
        return True
    alias = results.get("scheme_alias_detail") or results.get("schemeAliasDetail")
    if isinstance(alias, dict):
        if (alias.get("id") or alias.get("name") or alias.get("alias")):
            return True
    if results.get("alias_id") or results.get("aliasId"):
        return True
    return False


def _send_agreement_field_specs() -> list[dict]:
    """Ordered required fields for send agreement (label, category, validation source)."""
    return [
        {"fieldname": "aadhar_no", "label": _("Aadhar Number"), "category": "personal_bank"},
        {"fieldname": "driving_license_number", "label": _("DL number"), "category": "personal_bank"},
        {"fieldname": "pancard_number", "label": _("Pancard number"), "category": "personal_bank"},
        {
            "fieldname": "driving_license_issue_date",
            "label": _("DL issue date"),
            "category": "personal_bank",
        },
        {
            "fieldname": "bank_account_number",
            "label": _("Bank Account Number"),
            "category": "personal_bank",
        },
        {
            "fieldname": "driving_license_expiry_date",
            "label": _("DL expiry date"),
            "category": "personal_bank",
        },
        {"fieldname": "bank_ifsc", "label": _("Bank IFSC code"), "category": "personal_bank"},
        {"fieldname": "hub_fee", "label": _("Hub fee"), "category": "personal_bank"},
        {"fieldname": "lead_name", "label": _("Name"), "category": "personal_bank"},
        {
            "fieldname": "preferred_lang",
            "label": _("Preferred language"),
            "category": "personal_bank",
        },
        {"fieldname": "scheme", "label": _("Scheme"), "category": "personal_bank", "source": "portal"},
        {"fieldname": "current_state", "label": _("Current state"), "category": "address"},
        {"fieldname": "current_pincode", "label": _("Current pincode"), "category": "address"},
        {"fieldname": "current_landmark", "label": _("Current landmark"), "category": "address"},
        {
            "fieldname": "current_address_line1",
            "label": _("Current address line 1"),
            "category": "address",
        },
        {
            "fieldname": "current_address_proof_type",
            "label": _("Current address proof type"),
            "category": "address",
        },
        {
            "fieldname": "current_address_line2",
            "label": _("Current Address Line 2"),
            "category": "address",
        },
        {"fieldname": "current_city", "label": _("Current city"), "category": "address"},
        {
            "fieldname": "current_address_number",
            "label": _("Current address number"),
            "category": "address",
        },
        {
            "fieldname": "aadhaar_card_front",
            "label": _("Aadhaar card front"),
            "category": "documents",
            "attach": True,
        },
        {
            "fieldname": "aadhaar_card_back",
            "label": _("Aadhaar card back"),
            "category": "documents",
            "attach": True,
        },
        {
            "fieldname": "driving_license_front",
            "label": _("Driving License Front"),
            "category": "documents",
            "attach": True,
        },
        {
            "fieldname": "driving_license_back",
            "label": _("Driving License Back"),
            "category": "documents",
            "attach": True,
        },
        {"fieldname": "pancard_pic", "label": _("Pancard Pic"), "category": "documents", "attach": True},
        {
            "fieldname": "bank_passbook_pic",
            "label": _("Bank passbook pic"),
            "category": "documents",
            "attach": True,
        },
        {
            "fieldname": "current_address_proof",
            "label": _("Current address proof"),
            "category": "documents",
            "attach": True,
        },
    ]


def _is_send_agreement_field_filled(lead, spec: dict) -> bool:
    if spec.get("source") == "portal":
        account_id = (lead.custom_account_id or "").strip()
        return _portal_driver_has_scheme(account_id)
    fieldname = spec["fieldname"]
    if fieldname == "hub_fee":
        return lead.get("hub_fee") is not None
    if spec.get("attach"):
        return not _lead_field_missing(lead.get(fieldname), attach=True)
    return not _lead_field_missing(lead.get(fieldname))


def _get_send_agreement_requirements_payload(lead) -> dict:
    """Full send-agreement field status for API + validation."""
    specs = _send_agreement_field_specs()
    fields: list[dict] = []
    missing: list[str] = []

    for spec in specs:
        filled = _is_send_agreement_field_filled(lead, spec)
        fields.append(
            {
                "fieldname": spec["fieldname"],
                "label": spec["label"],
                "category": spec["category"],
                "filled": filled,
            }
        )
        if not filled:
            missing.append(spec["label"])

    category_titles = [
        ("personal_bank", _("Personal & Bank Details")),
        ("address", _("Address Information")),
        ("documents", _("Required Documents")),
    ]
    categories = []
    for key, title in category_titles:
        missing_fields = [
            {"fieldname": f["fieldname"], "label": f["label"]}
            for f in fields
            if f["category"] == key and not f["filled"]
        ]
        categories.append({"key": key, "title": title, "missing_fields": missing_fields})

    filled_count = sum(1 for f in fields if f["filled"])
    total_count = len(fields)

    return {
        "missing": missing,
        "missing_count": len(missing),
        "filled_count": filled_count,
        "total_count": total_count,
        "can_send": len(missing) == 0,
        "categories": categories,
        "fields": fields,
    }


def _get_send_agreement_missing_fields(lead) -> list[str]:
    """Return human-readable labels for fields still required before send agreement."""
    return _get_send_agreement_requirements_payload(lead)["missing"]


def _validate_send_agreement_lead_fields(lead) -> None:
    """Raise when CRM Lead / portal fields required for send agreement are incomplete."""
    missing = _get_send_agreement_missing_fields(lead)
    if missing:
        frappe.throw(
            _("Complete required fields before sending agreement: {0}").format(
                ", ".join(missing)
            )
        )


@frappe.whitelist()
def get_send_agreement_requirements(leadId: str):
    """Return missing field labels for the Agreement tab UI."""
    lid = (leadId or "").strip()
    if not lid:
        frappe.throw(_("Lead ID is required"))
    if not frappe.db.exists("CRM Lead", lid):
        frappe.throw(_("Not a valid CRM Lead"))

    lead = frappe.get_doc("CRM Lead", lid)
    return _get_send_agreement_requirements_payload(lead)


def _format_update_driver_validation_errors(exc: ValidationError) -> list[dict]:
    """Shape Pydantic errors for API clients (field + message + type)."""
    rows: list[dict] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        parts: list[str] = []
        for p in loc:
            if isinstance(p, str):
                parts.append(p)
            else:
                parts.append(str(p))
        field = parts[-1] if parts else "data"
        msg = err.get("msg", "")
        if not isinstance(msg, str):
            msg = str(msg)
        rows.append(
            {
                "field": field,
                "code": str(err.get("type", "") or ""),
                "message": msg,
            }
        )
    return rows


def _raise_update_driver_validation_error(exc: ValidationError) -> None:
    v_errors = _format_update_driver_validation_errors(exc)
    summary = (
        v_errors[0]["message"]
        if len(v_errors) == 1
        else _("{0} validation issues").format(len(v_errors))
    )
    throw_custom_api_error(
        summary,
        api_code=CrmApiErrors.UPDATE_DRIVER_VALIDATION,
        title=_("Driver update"),
        details={"validation_errors": v_errors},
        http_status_code=422,
    )


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
    url = f"{base}/api/v1/driver/aggrementHistory/bydriverWise"
    print(url)
    params = {"accountId": account_id}
    headers = {"Authorization": token}

    try:
        response = re.get(url, params=params, headers=headers, timeout=60)
    except re.exceptions.RequestException as e:
        logger.exception("Carrum agreements request failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    try:
        body = response.json()
        print(body)
    except ValueError:
        logger.error(
            "Carrum agreements non-JSON response (HTTP %s): %s",
            response.status_code,
            (response.text or "")[:500],
        )
        frappe.throw(_("Invalid response from Carrum"))

    print("====================body============================")
    print(body)
    print(response.status_code)
    print("================================================")
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
def view_agreement(digio_id: str):
    """
    Proxy Carrum GET /api/v1/driver/agreement/pdf/{digio_id}. Returns PDF as base64 for SPA preview/download.
    """
    did = (digio_id or "").strip()
    if not did:
        frappe.throw(_("Digio ID is required"))

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    url = f"{base}/api/v1/driver/agreement/pdf/{did}"
    headers = {
        "Authorization": token,
        "Accept": "application/pdf, application/octet-stream, */*",
    }

    try:
        response = re.get(url, headers=headers, timeout=120)
    except re.exceptions.RequestException as e:
        logger.exception("view_agreement request failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    if not response.ok:
        logger.error(
            "view_agreement HTTP %s: %s",
            response.status_code,
            (response.text or "")[:1000],
        )
        frappe.throw(
            _("Carrum agreement PDF error ({0})").format(response.status_code)
        )

    content = response.content or b""
    if not content:
        frappe.throw(_("Empty PDF response from Carrum"))

    ct_header = response.headers.get("Content-Type") or "application/pdf"
    content_type = ct_header.split(";")[0].strip().lower()
    if "pdf" not in content_type and "octet-stream" not in content_type:
        sample = content[:200].decode("utf-8", errors="replace")
        if sample.lstrip().startswith("<"):
            logger.warning(
                "view_agreement: non-PDF body for %s: %s", did, sample[:80]
            )

    b64 = base64.b64encode(content).decode("ascii")
    return {
        "success": True,
        "filename": f"agreement-{did}.pdf",
        "content_type": content_type or "application/pdf",
        "file_content_b64": b64,
    }

@frappe.whitelist()
def get_digio_agreement(digio_id: str):
    did = (digio_id or "").strip()
    if not did:
        frappe.throw(_("Digio ID is required"))

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    url = f"{base}/api/v1/driver/agreement/pdf/{did}"
    headers = {
        "Authorization": token,
        "Accept": "application/pdf, application/octet-stream, */*",
    }

    try:
        response = re.get(url, headers=headers, timeout=120)
    except re.exceptions.RequestException as e:
        logger.exception("view_agreement request failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    if not response.ok:
        logger.error(
            "view_agreement HTTP %s: %s",
            response.status_code,
            (response.text or "")[:1000],
        )
        frappe.throw(
            _("Carrum agreement PDF error ({0})").format(response.status_code)
        )
    
    frappe.local.response.filename = f"agreement_{digio_id}.pdf"
    frappe.local.response.filecontent = response.content
    frappe.local.response.type = "download"

@frappe.whitelist()
def send_agreement(leadId: str):
    lid = (leadId or "").strip()
    if not lid:
        frappe.throw(_("Lead ID is required"))
    if not frappe.db.exists("CRM Lead", lid):
        frappe.throw(_("Not a valid CRM Lead"))

    lead = frappe.get_doc("CRM Lead", lid)
    account_id = (lead.custom_account_id or "").strip()
    if not account_id:
        frappe.throw(_("Carrum Driver Account ID is required on the lead"))

    _validate_send_agreement_lead_fields(lead)

    phoneNo = lead.mobile_no
    driver_name = lead.lead_name
    aadhar_number = lead.aadhar_no
    pan_card = lead.pancard_number
    dl_number = lead.driving_license_number
    dl_issue_date = lead.driving_license_issue_date
    dl_expiry_date = lead.driving_license_expiry_date
    email = lead.email
    bank_account_number = lead.bank_account_number
    lead_pk = lead.name
    bank_ifsc_code = lead.bank_ifsc
    lead_hub_id = lead.hub_id
    current_address_line1 = lead.current_address_line1
    current_address_line2 = lead.current_address_line2
    current_city = lead.current_city
    current_state = lead.current_state
    
    current_pincode = lead.current_pincode
    current_landmark = lead.current_landmark
    current_address = ""
    if current_address_line1:
        current_address += current_address_line1
    if current_address_line2:
        current_address += ", " + current_address_line2
    if current_landmark:
        current_address += ", " + current_landmark
    if current_city:
        current_address += ", " + current_city
    if current_state:
        current_address += ", " + current_state
    if current_pincode:
        current_address += ", " + current_pincode

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    url = f"{base}/api/v1/driver/sendAgreementForDriver"
    
    payload = {
        "accountId": account_id,
        "driver_phone": phoneNo,
        "driver_name": driver_name,
        "driver_current_address": current_address,
        "aadhar_number": aadhar_number,
        "pan_card": pan_card,
        "dl_number": dl_number,
        "dl_issue_date": _date_to_json_value(dl_issue_date),
        "dl_expiry_date": _date_to_json_value(dl_expiry_date),
        "driver_email": email,
        "driver_bank_account_number": bank_account_number,
        "driver_small_id": lead_pk,
        "bank_ifsc_code": bank_ifsc_code,
        "Witness1": "relative_name", # relative_name
        "Witness2": "previous_employer_name", # previous_employer_name
        "Witness3": "father_name", # father_name
        "Witness4": "sarpanch", # sarpanch
        "hubId": lead_hub_id
    }
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    try:
        response = re.post(url=url, headers=headers, json=payload, timeout=60)
    except re.exceptions.RequestException as e:
        logger.exception("send_agreement failed: %s", e)
        frappe.throw(_("Could not reach Carrum"))

    try:
        resp_body = response.json()
    except ValueError:
        frappe.throw(_("Invalid response from Carrum"))

    if not response.ok:
        logger.error("send_agreement error: %s", resp_body)
        frappe.throw(
            resp_body.get("message")
            or resp_body.get("error")
            or _("Carrum API error ({0})").format(response.status_code)
        )

    return {"success": True, "data": resp_body}


@frappe.whitelist(methods=["POST"])
def upload_agreement(leadId: str | None = None):
    """
    Forward offline agreement image to Carrum (multipart: ``image`` + ``docType``).

    Expects ``multipart/form-data`` with file field ``image`` and lead id ``leadId``.
    """
    lid = (leadId or "").strip()
    if not lid:
        frappe.throw(_("Lead ID is required"))
    if not frappe.db.exists("CRM Lead", lid):
        frappe.throw(_("Not a valid CRM Lead"))

    lead = frappe.get_doc("CRM Lead", lid)
    account_id = (lead.custom_account_id or "").strip()
    if not account_id:
        frappe.throw(_("Carrum Driver Account ID is required on the lead"))

    files_dict = frappe.request.files or {}
    file_part = files_dict.get("image")
    if file_part is None or getattr(file_part, "filename", None) in (None, ""):
        frappe.throw(_("Image file is required (form field: image)"))

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    url = f"{base}/api/v1/driver/uploadDocsByAccount/{account_id}"
    headers = {"Authorization": token}

    raw = file_part.read()
    if not raw:
        frappe.throw(_("Uploaded file is empty"))

    filename = file_part.filename or "agreement-upload.bin"
    content_type = getattr(file_part, "content_type", None) or "application/octet-stream"

    data = {"docType": "offline_aggrement_pic"}
    files = {"image": (filename, raw, content_type)}

    try:
        response = re.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
    except re.exceptions.RequestException as e:
        logger.exception("upload_agreement failed: %s", e)
        frappe.throw(_("Could not reach Carrum: {0}").format(str(e)))

    try:
        resp_body = response.json()
    except ValueError:
        resp_body = {"_raw": (response.text or "")[:500]}

    if not response.ok:
        logger.error(
            "upload_agreement HTTP %s: %s",
            response.status_code,
            json.dumps(resp_body, default=str)[:1000],
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
        frappe.throw(
            message or _("Carrum upload error ({0})").format(response.status_code)
        )

    return {"success": True, "data": resp_body}


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
    headers = {"Authorization": token}

    try:
        response = re.get(url, headers=headers)
    except re.exceptions.RequestException as e:
        logger.exception("get_portal_driver_detail request failed: %s", e)
        return {"success": False, "message": "Failed to get driver details"}
    
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


def _lead_blocks_scheme_business_type_change(lead) -> bool:
    """True when CRM Lead status forbids changing scheme / business type."""
    if isinstance(lead, str):
        if not frappe.db.exists("CRM Lead", lead):
            return False
        lead = frappe.get_doc("CRM Lead", lead)
    primary = (getattr(lead, "primary_status", None) or "").strip().lower()
    if primary == "drop":
        return True
    status_name = (getattr(lead, "status", None) or "").strip()
    if not status_name:
        return False
    row = frappe.db.get_value(
        "CRM Lead Status",
        status_name,
        ["custom_primary_status", "is_apply_on_vehicle_assignment"],
        as_dict=True,
    )
    if not row:
        return False
    if (row.get("custom_primary_status") or "").strip().lower() == "drop":
        return True
    return bool(row.get("is_apply_on_vehicle_assignment"))


def _parse_update_driver_payload(data) -> UpdateDriverDtoSchema:
    """Accept dict (preferred) or legacy JSON string from ``frappe.form_dict``."""
    if data is None:
        frappe.throw(_("data is required"))
    if isinstance(data, dict):
        if not data:
            frappe.throw(_("data is required"))
        try:
            return UpdateDriverDtoSchema.model_validate(data)
        except ValidationError as e:
            _raise_update_driver_validation_error(e)
    if isinstance(data, str):
        raw = data.strip()
        if not raw:
            frappe.throw(_("data is required"))
        try:
            return UpdateDriverDtoSchema.model_validate_json(raw)
        except ValidationError as e:
            _raise_update_driver_validation_error(e)
    frappe.throw(_("data must be a JSON object or string"))


@frappe.whitelist()
def update_driver(account_id: str, data: dict | str | None = None):
    """
    :param account_id: Carrum driver account id (CRM Lead Hub ID when aligned).
    :param data: JSON object (or legacy JSON string) with ``scheme_id`` and optional ``scheme_type`` (forwarded to Carrum PUT).
    """
    aid = (account_id or "").strip()
    if not aid:
        frappe.throw(_("Account ID is required"))

    payload = _parse_update_driver_payload(data)

    scheme_change_requested = (
        payload.scheme_id is not None
        or payload.scheme_type is not None
        or payload.tenure is not None
        or payload.emi_id is not None
        or payload.remove_emi is not None
    )
    if scheme_change_requested:
        lead_name = frappe.db.get_value("CRM Lead", {"custom_account_id": aid}, "name")
        if lead_name and _lead_blocks_scheme_business_type_change(lead_name):
            frappe.throw(
                _(
                    "Business type and scheme cannot be changed when the lead is in Drop status or after vehicle assignment."
                )
            )

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    token = frappe.conf.get("old_carrum_token")
    if not token:
        frappe.throw(_("Old Carrum token is not configured (old_carrum_token)"))

    body: dict = {}
    sid = payload.scheme_id
    if sid is not None and str(sid).strip() != "":
        if isinstance(sid, (int, float)) and not isinstance(sid, bool):
            body["scheme_id"] = int(sid)
        else:
            s = str(sid).strip()
            if s.isdigit():
                body["scheme_id"] = int(s)
            else:
                body["scheme_id"] = s

    if payload.scheme_type:
        body["scheme_type"] = payload.scheme_type

    if payload.tenure is not None and payload.emi_id is not None:
        body['tenure'] = payload.tenure
        body['emi_id'] = payload.emi_id


    if payload.remove_emi is not None:
        body['remove_emi'] = payload.remove_emi

    if payload.uber_id is not None:
        body['driver_uber_id'] = str(payload.uber_id)

    if "vendor" in (payload.old_scheme_name or "") or "double driver" in (payload.old_scheme_name or "") :
        lead = frappe.get_doc("CRM Lead", {"custom_account_id": aid})
        if lead:
            util_service.un_assign_secondary_lead_from_lead(lead.name)
        else:
            frappe.throw(_("Lead not found with account ID: {0}").format(aid))

    if not body:
        return {"success": True}

    print(body)
    url = f"{base}/api/v1/driver/update/{aid}?idType=account"
    headers = {"Authorization": token, "Content-Type": "application/json"}

    try:
        response = re.put(url, headers=headers, json=body, timeout=60)
        print(response.text)
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

    # Scheme / EMI changes can alter portal wallet balances; align CRM Lead status with
    # PSD/FSD stages (same rules as payment capture — see maybe_update_lead_status_after_payment_capture).
    _scheme_or_emi_keys = (
        "scheme_id",
        "scheme_type",
        "tenure",
        "emi_id",
        "remove_emi",
    )
    if body and any(k in body for k in _scheme_or_emi_keys):
        from core.api.carrum_payment import maybe_update_lead_status_after_payment_capture

        lead_name = frappe.db.get_value("CRM Lead", {"custom_account_id": aid}, "name")
        if lead_name:
            lead = frappe.get_doc("CRM Lead", lead_name)
            maybe_update_lead_status_after_payment_capture(lead)

    return {"success": True, "data": resp_body}

@frappe.whitelist(methods=["POST"])
def lead_creation_webhook():
    """
    Carrum webhook: JSON body ``mobile_no``, ``displayId`` (CRM Lead ``name``, AAAA0001–ZZZZ9999),
    and optional ``source``.

    Creates a lead with **exactly** ``displayId`` as the document name (via ``insert(set_name=…)`` —
    required because Frappe otherwise clears ``name`` for naming_series autoname).
    """
    
    data = frappe.request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    raw_display = data.get("displayId")

    displayId = str(raw_display).strip().upper() if raw_display is not None else ""
    phone_raw =  data.get("phone")
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
        return "Lead already exists"

    lead = frappe.new_doc("CRM Lead")
    lead.flags.skip_crm_lead_auto_id = True
    lead.mobile_no = mobile_no
    if not apply_default_crm_lead_status_to_doc(lead):
        frappe.throw(
            _("No CRM Lead Status is configured. Add one in CRM Lead Status."),
            frappe.ValidationError,
        )
    lead.lead_type = "DRIVER"
    lead.lead_name = None

    meta = frappe.get_meta("CRM Lead")
    if source and meta.get_field("source"):
        lead.set("source", source)

    lead.insert(set_name=displayId, ignore_permissions=True)

    logger.info("lead_creation_webhook: created CRM Lead %s", lead.name)
    return {"message": "ok", "name": lead.name, "created": True}


def _apply_webhook_crm_lead_status_row(lead, status_filters, not_found_message: str):
    """Map CRM Lead Status row onto lead: primary ← custom_primary_status, secondary ← lead_status, status ← name.

    External driver-status webhooks are authoritative and may move a lead out of
    a closed primary bucket (e.g. ``Drop`` → onboarded), so the agent-level
    transition lock is bypassed here via ``flags.ignore_status_change_lock``.
    """
    row = frappe.db.get_value(
        EnumValues.ReferenceDocType.CRM_LEAD_STATUS,
        status_filters,
        ["custom_primary_status", "lead_status", "name"],
    )
    if not row or row[2] is None:
        frappe.throw(not_found_message)
    lead.primary_status = row[0]
    lead.secondary_status = row[1]
    lead.status = row[2]
    lead.flags.ignore_status_change_lock = True
    lead.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def driver_status_update_webhook():
    payload = frappe.request.get_json() or {}
    account_id = payload.get("accountId")
    if not account_id:
        frappe.throw(_("accountId is required"))

    lead_name = frappe.db.get_value(
        "CRM Lead", {"custom_account_id": account_id}, "name"
    )
    if not lead_name:
        frappe.throw(_("Lead not found with account ID: {0}").format(account_id))

    lead = frappe.get_doc("CRM Lead", lead_name)

    new_status = payload.get("newStatus")
    if new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.ONBOARDED:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_apply_on_vehicle_assignment": 1},
            _("Lead status not found with is_apply_on_vehicle_assignment = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.PERMANENT_DROP:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_permanent_drop": 1},
            _("Lead status not found with is_permanent_drop = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.TEMP_DROP:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_temp_drop": 1},
            _("Lead status not found with is_temp_drop = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.RECOVERY_INITIATED:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_recovery_initiated": 1},
            _("Lead status not found with is_recovery_initiated = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.RECOVERY_DONE:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_recovery_done": 1},
            _("Lead status not found with is_recovery_done = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.MAINTENANCE_DROP:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_maintenance_drop": 1},
            _("Lead status not found with is_maintenance_drop = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.DRIVER_RETURNED:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_driver_returned": 1},
            _("Lead status not found with is_driver_returned = 1"),
        )
    elif new_status ==  EnumValues.OLD_SYSTEM_DRIVER_STATUS.INACTIVE:
        _apply_webhook_crm_lead_status_row(
            lead,
            {"is_inactive": 1},
            _("Lead status not found with is_inactive = 1"),
        )
    elif new_status == EnumValues.OLD_SYSTEM_DRIVER_STATUS.TO_ONBOARD:
        pass # no action required
    else:
        frappe.throw(_("Unhandled status: {0}").format(new_status))

    return {"message": "ok"}

def raise_driver_return_request(
    oldCarrumAccountId: str, identificationType: str, requestReason: str
):
    if not oldCarrumAccountId:
        frappe.throw(_("oldCarrumAccountId is required"))

    base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
    if not base:
        frappe.throw(_("Old Carrum base URL is not configured (old_carrum_base_url)"))

    url = f"{base}/api/v1/management/reonboarding"
    body = {
        "old_account_id": oldCarrumAccountId,
        "identification_key": identificationType,
        "request_reason": requestReason,
    }
    request_by = (
        fetch_carrum_user_data_using_frappe_username(frappe.session.user).get("id")
    )
    if not request_by:
        frappe.throw(_("Carrum user id not found for current user"))
    body["request_by"] = request_by
    old_carrum_token = frappe.conf.get("old_carrum_token")
    headers = {"Authorization": old_carrum_token, "Content-Type": "application/json"}
    response = re.post(url, headers=headers, json=body, timeout=60)

    try:
        response_data = response.json()
    except ValueError:
        response_data = None

    if not response.ok:
        msg = response.text or str(response.status_code)
        if isinstance(response_data, dict) and response_data.get("message"):
            msg = response_data.get("message")
        frappe.throw(_("Failed to raise driver return request: {0}").format(msg))

    if not response_data:
        frappe.throw(_("Invalid response from driver service"))

    if response_data.get("status") == "success":
        return True

    err = response_data.get("message") or response_data.get("error") or _("Request was not successful")
    frappe.throw(_("Failed to raise driver return request: {0}").format(err))
