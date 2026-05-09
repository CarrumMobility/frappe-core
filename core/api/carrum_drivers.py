import base64
import json
from uuid import UUID
from core.constants.enums import EnumValues
from crm.api.api_errors import CrmApiErrors, throw_custom_api_error
from crm.api.lead import unAssignSecondaryLeadFromLead
from crm.fcrm.doctype.crm_lead.crm_lead import LEAD_ID_PATTERN, apply_default_crm_lead_status_to_doc
from crm.utils import parse_phone_number
import requests as re

import frappe
from frappe import _

from typing import Optional

from pydantic import BaseModel, ValidationError, field_validator


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
        "dl_issue_date": dl_issue_date,
        "dl_expiry_date": dl_expiry_date,
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
    print("====================payload============================")
    print(payload)
    print("====================payload============================")
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
        print(response.text)
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
        print(response)
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
            unAssignSecondaryLeadFromLead(lead.name)
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

@frappe.whitelist(methods=["POST"])
def driver_status_update_webhook():
    payload = frappe.request.get_json()    # {'driverId': 'eb320a30-44ca-4b81-812c-c971cca3ce61', 'accountId': 'dc485de4-4cd6-41e7-94d5-6f617ea81c60', 'smallId': 'AAAA0017', 'previousStatus': 'created', 'newStatus': 'onboarded'}
    accountId = payload.get("accountId")
    lead = frappe.get_doc("CRM Lead", {"custom_account_id": accountId})
    if not lead:
        frappe.throw(_("Lead not found with account ID: {0}").format(accountId))
        return

    newStatus = payload.get("newStatus")
    if newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.ONBOARDED:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_apply_on_vehicle_assignment": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_apply_on_vehicle_assignment = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.PERMANENT_DROP:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_permanent_drop": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_permanent_drop = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.TEMP_DROP:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_temp_drop": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}

        else:
            frappe.throw(_("Lead status not found with is_temp_drop = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.RECOVERY_INITIATED:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_recovery_initiated": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_recovery_initiated = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.RECOVERY_DONE:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_recovery_done": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_recovery_done = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.MAINTENANCE_DROP:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_maintenance_drop": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_maintenance_drop = 1"))
    elif newStatus == EnumValues.OLD_SYSTEM_DRIVER_STATUS.DRIVER_RETURNED:
        leadStatus = frappe.db.get_value(EnumValues.ReferenceDocType.CRM_LEAD_STATUS, {"is_driver_returned": 1}, "custom_primary_status")
        if leadStatus:
            lead.primary_status = leadStatus
            lead.secondary_status = leadStatus
            lead.status = leadStatus
            lead.save(ignore_permissions=True)
            return {"message": "ok"}
        else:
            frappe.throw(_("Lead status not found with is_driver_returned = 1"))
    else:
        frappe.throw(_("Unhandled status: {0}").format(newStatus))