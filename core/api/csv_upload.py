import csv
import io
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import get_datetime

from core.constants.enums import EnumValues
from core.s3_file_storage import file_uses_s3, s3_client, s3_object_key, s3_enabled
from core.services import logged_requests as requests
from crm.fcrm.doctype.crm_lead.crm_lead import (
    apply_default_crm_lead_status_to_doc,
    get_next_crm_lead_id,
    normalize_crm_lead_india_phone,
)

logger = frappe.logger("core.api.csv_upload")
logger.setLevel(logging.INFO)

NO_VALUE_FIELD_TYPES = {
    "Section Break",
    "Column Break",
    "Tab Break",
    "HTML",
    "Button",
    "Fold",
    "Table",
    "Table MultiSelect",
}
BATCH_COMMIT_SIZE = 1000
MAX_ROW_RESULTS = 200
SYSTEM_FIELD_MAP = {
    "uploaded_at": "creation",
    "creation_uploaded_at": "creation",
    "creation": "creation",
}


def _normalize_header(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


@contextmanager
def _open_csv_from_file_url(file_url: str):
    file_url = (file_url or "").strip()
    if not file_url:
        frappe.throw(_("CSV file URL is required"))

    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if file_name:
        file_doc = frappe.get_doc("File", file_name)
        if s3_enabled() and file_uses_s3(file_doc):
            key = s3_object_key(file_doc)
            if not key:
                frappe.throw(_("Cannot resolve S3 object key for this file"))
            obj = s3_client().get_object(Bucket=frappe.conf.s3_bucket, Key=key)
            body = obj["Body"]
            stream = io.TextIOWrapper(body, encoding="utf-8-sig", newline="")
            try:
                yield stream
            finally:
                stream.detach()
                body.close()
            return

        full_path = file_doc.get_full_path()
        if not os.path.exists(full_path):
            frappe.throw(_("File not found for URL: {0}").format(file_url))
        with open(full_path, mode="r", encoding="utf-8-sig", newline="") as stream:
            yield stream
        return

    if not file_url.startswith(("http://", "https://")):
        frappe.throw(_("File not found for URL: {0}").format(file_url))

    response = requests.get(file_url, timeout=60, stream=True)
    try:
        response.raise_for_status()
        response.raw.decode_content = True
        stream = io.TextIOWrapper(response.raw, encoding="utf-8-sig", newline="")
        try:
            yield stream
        finally:
            stream.detach()
    finally:
        response.close()


def _crm_lead_field_map():
    meta = frappe.get_meta(EnumValues.ReferenceDocType.CRM_LEAD)
    field_map = {"name": "name"}

    for field in meta.fields:
        if field.fieldtype in NO_VALUE_FIELD_TYPES or field.read_only:
            continue
        field_map[_normalize_header(field.fieldname)] = field.fieldname
        if field.label:
            field_map[_normalize_header(field.label)] = field.fieldname

    field_map.update(
        {
            "name": "name",
            "lead_id": "name",
            "crm_lead": "name",
            "crm_lead_id": "name",
            "mobile": "mobile_no",
            "mobile_number": "mobile_no",
            "mobile_no": "mobile_no",
            "alternate_mobile_no": "alternate_phone",
            "alternate_mobile_number": "alternate_phone",
            "alternate_phone": "alternate_phone",
            "phone_number": "mobile_no",
            "account_id": "custom_account_id",
            "first_business_type": "preferred_business_type_1",
            "first_business_scheme": "preferred_scheme_1",
            "second_business_type": "preferred_business_type_2",
            "second_business_scheme": "preferred_scheme_2",
            "second_busines_scheme": "preferred_scheme_2",
            "uploaded_source": "upload_source",
            "source_name": "source",
            "status_id": "status",
            "hub_name": "custom_hub_name",
        }
    )
    return field_map


def _extract_lead_payload(row: dict, field_map: dict) -> tuple[dict, list[str]]:
    payload = {}
    system_values = {}
    skipped_columns = []

    for header, value in row.items():
        normalized_header = _normalize_header(header)
        system_field = SYSTEM_FIELD_MAP.get(normalized_header)
        fieldname = field_map.get(normalized_header)
        if not fieldname and not system_field:
            skipped_columns.append(header)
            continue

        if value is None:
            continue
        value = str(value).strip()
        if value == "":
            continue
        if system_field:
            system_values[system_field] = value
        else:
            payload[fieldname] = value

    if system_values:
        payload["_system_values"] = system_values
    return payload, skipped_columns


def _parse_uploaded_at(value: str | None):
    value = str(value or "").strip()
    if not value:
        return None

    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return get_datetime(value)


def _apply_system_values(lead_name: str, system_values: dict | None) -> None:
    if not system_values:
        return

    updates = {}
    if system_values.get("creation"):
        updates["creation"] = _parse_uploaded_at(system_values.get("creation"))

    updates = {k: v for k, v in updates.items() if v is not None}
    if updates:
        frappe.db.set_value(
            EnumValues.ReferenceDocType.CRM_LEAD,
            lead_name,
            updates,
            update_modified=False,
        )


def _find_existing_crm_lead(payload: dict) -> str | None:
    # lead_name = (payload.get("name") or "").strip()
    # if lead_name and frappe.db.exists(EnumValues.ReferenceDocType.CRM_LEAD, lead_name):
    #     return lead_name

    mobile_no = (payload.get("mobile_no") or "").strip()
    if mobile_no:
        payload["mobile_no"] = normalize_crm_lead_india_phone(
            mobile_no, _("Mobile number"), is_mobile=True
        )

    for fieldname in ("mobile_no", "custom_account_id"):
        value = (payload.get(fieldname) or "").strip()
        if value:
            existing = frappe.db.get_value(
                EnumValues.ReferenceDocType.CRM_LEAD,
                {fieldname: value},
                "name",
            )
            if existing:
                return existing

    return None


def _rename_existing_lead_if_required(lead) -> str:
    if (lead.get("lead_type") or "").strip().upper() != EnumValues.LeadType.LEAD:
        return lead.name

    old_name = lead.name
    new_name = get_next_crm_lead_id()
    frappe.rename_doc(
        EnumValues.ReferenceDocType.CRM_LEAD,
        old_name,
        new_name,
        force=True,
        show_alert=False,
    )
    logger.info(
        "CRM Lead CSV import renamed existing LEAD before update: old_name=%s new_name=%s",
        old_name,
        new_name,
    )
    return new_name


def _upsert_crm_lead(payload: dict) -> tuple[str, str]:
    system_values = payload.pop("_system_values", None)
    existing_name = _find_existing_crm_lead(payload)
    payload.pop("name", None)

    if existing_name:
        lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, existing_name)
        action = "updated"
        new_name = _rename_existing_lead_if_required(lead)
        if new_name != existing_name:
            lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, new_name)
            action = "renamed_updated"

        for fieldname, value in payload.items():
            lead.set(fieldname, value)
        lead.save(ignore_permissions=True)
        _apply_system_values(lead.name, system_values)
        return lead.name, action

    lead = frappe.new_doc(EnumValues.ReferenceDocType.CRM_LEAD)

    apply_default_crm_lead_status_to_doc(lead)

    for fieldname, value in payload.items():
        lead.set(fieldname, value)

    lead.insert(ignore_permissions=True)
    _apply_system_values(lead.name, system_values)
    return lead.name, "created"


@frappe.whitelist()
def upload_csv(file_url: str):
    started_at = time.monotonic()
    logger.info("CRM Lead CSV import started for file_url=%s", file_url)

    field_map = _crm_lead_field_map()
    created = 0
    updated = 0
    failed = 0
    processed = 0
    skipped_columns = set()
    row_results = []

    with _open_csv_from_file_url(file_url) as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            frappe.throw(_("CSV file must contain a header row"))

        logger.info(
            "CRM Lead CSV import headers detected: %s",
            ", ".join(reader.fieldnames or []),
        )

        for row_number, row in enumerate(reader, start=2):
            processed += 1
            save_point = f"crm_lead_csv_row_{row_number}"
            frappe.db.savepoint(save_point)
            try:
                payload, skipped = _extract_lead_payload(row, field_map)
                skipped_columns.update(skipped)

                if not payload:
                    failed += 1
                    if len(row_results) < MAX_ROW_RESULTS:
                        row_results.append(
                            {
                                "row": row_number,
                                "success": False,
                                "error": _("No valid CRM Lead columns found"),
                            }
                        )
                    continue

                lead_name, action = _upsert_crm_lead(payload)
                if action == "created":
                    created += 1
                else:
                    updated += 1
                if len(row_results) < MAX_ROW_RESULTS:
                    row_results.append(
                        {
                            "row": row_number,
                            "success": True,
                            "action": action,
                            "name": lead_name,
                        }
                    )
            except Exception as exc:
                failed += 1
                frappe.db.rollback(save_point=save_point)
                logger.exception("CRM Lead CSV import failed for row %s", row_number)
                logger.info(
                    "CRM Lead CSV import progress after failure: processed=%s created=%s updated=%s failed=%s",
                    processed,
                    created,
                    updated,
                    failed,
                )
                if len(row_results) < MAX_ROW_RESULTS:
                    row_results.append(
                        {
                            "row": row_number,
                            "success": False,
                            "error": str(exc),
                        }
                    )

            if processed % BATCH_COMMIT_SIZE == 0:
                frappe.db.commit()
                elapsed = time.monotonic() - started_at
                rows_per_second = round(processed / elapsed, 2) if elapsed else processed
                logger.info(
                    "CRM Lead CSV import batch committed: processed=%s created=%s updated=%s failed=%s elapsed_seconds=%.2f rows_per_second=%s",
                    processed,
                    created,
                    updated,
                    failed,
                    elapsed,
                    rows_per_second,
                )

    elapsed = time.monotonic() - started_at
    logger.info(
        "CRM Lead CSV import finished: success=%s processed=%s created=%s updated=%s failed=%s skipped_columns=%s elapsed_seconds=%.2f",
        failed == 0,
        processed,
        created,
        updated,
        failed,
        sorted(c for c in skipped_columns if c),
        elapsed,
    )

    return {
        "success": failed == 0,
        "processed": processed,
        "created": created,
        "updated": updated,
        "failed": failed,
        "skipped_columns": sorted(c for c in skipped_columns if c),
        "row_results_limited_to": MAX_ROW_RESULTS,
        "rows": row_results,
    }
