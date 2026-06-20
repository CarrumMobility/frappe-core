import datetime
import logging
import time

import frappe
from frappe import _
from frappe.utils import now
from frappe.utils.synchronization import filelock

from core.constants.enums import EnumValues
from crm.api.lead import get_next_lead_id

logger = frappe.logger("core.api.csv_upload")
logger.setLevel(logging.INFO)

RAW_LEAD_TABLE = "temp_lead_raw_data"
BATCH_SIZE = 2000
ADMIN_USER = "Administrator"
NEW_LEAD_FIELDS = [
    "name",
    "creation",
    "modified",
    "modified_by",
    "owner",
    "docstatus",
    "idx",
    "mobile_no",
    "lead_type",
    "status",
    "primary_status",
    "secondary_status",
    "lead_uploaded_at",
    "source",
    "source_id",
]

cache = frappe.cache()

@frappe.whitelist()
def upsert_upload_key_in_redis(is_upload: bool):
    cache.set_value("continue_lead_processing", int(is_upload), expires_in_sec=60*60*48)

    return True

def _mark_raw_row(mobile_no, *, is_processed, error=None):
    if not mobile_no:
        return
    frappe.db.sql(
        f"""
        UPDATE `{RAW_LEAD_TABLE}`
        SET is_processed = %s, processing_error = %s
        WHERE mobile_no = %s
        """,
        (is_processed, error, mobile_no),
    )


def _parse_uploaded_at(value):
    if not value:
        return None
    return datetime.datetime.strptime(value, "%d-%m-%Y %H:%M")


def _build_new_lead_values(row, lead_id, ts):
    return {
        "name": lead_id,
        "creation": ts,
        "modified": ts,
        "modified_by": ADMIN_USER,
        "owner": ADMIN_USER,
        "docstatus": 0,
        "idx": 0,
        "mobile_no": (row.get("mobile_no") or "").strip(),
        "lead_type": EnumValues.LeadType.LEAD,
        "status": row.get("status_id"),
        "primary_status": row.get("primary_status"),
        "upload_source": row.get("uploaded_source"),
        "secondary_status": row.get("secondary_status"),
        "lead_uploaded_at": _parse_uploaded_at(row.get("uploaded_at")) or ts,
        "source": row.get("source_name"),
        "source_id": row.get("source_id"),
    }


def _bulk_insert_new_leads(leads):
    if not leads:
        return
    frappe.db.bulk_insert(
        "CRM Lead",
        NEW_LEAD_FIELDS,
        [tuple(lead.get(field) for field in NEW_LEAD_FIELDS) for lead in leads],
    )


@frappe.whitelist()
def process_lead_from_raw_to_lead_table():
    upsert_upload_key_in_redis(True)

    frappe.enqueue(
        method="core.api.csv_upload.process_lead_from_raw_to_lead_table_consumer",
        queue="long",
        # timeout=60 * 60 * 24,
    )

    return True


def process_lead_from_raw_to_lead_table_consumer():
    processed = created = updated = failed = 0
    started_at = time.monotonic()

    while True:
        is_upload = cache.get_value("continue_lead_processing")
        if not is_upload or is_upload == 0:
            logger.info("Upload key not found in redis or is 0, stopping lead processing")
            break

        rows = frappe.db.sql(
            f"SELECT * FROM `{RAW_LEAD_TABLE}` WHERE is_processed = 0 LIMIT %s FOR UPDATE",
            (BATCH_SIZE,),
            as_dict=True,
        )
        if not rows:
            break

        batch_started_at = time.monotonic()
        batch_processed = batch_created = batch_updated = batch_failed = 0
        pending_new_leads = []

        for row in rows:
            mobile_no = row.get("mobile_no")
            with filelock(f"lead_processing_lock_{mobile_no}", timeout=60 * 60, is_global=True):
                if not mobile_no:
                    failed += 1
                    batch_failed += 1
                    _mark_raw_row(row.get("mobile_no"), is_processed=1, error="Missing mobile number")
                    frappe.db.commit()
                    continue
                try:
                    lead_name = frappe.db.get_value("CRM Lead", {"mobile_no": mobile_no}, "name")

                    if lead_name:
                        frappe.db.get_value("CRM Lead", lead_name, "name", for_update=True)
                        lead_type = frappe.db.get_value("CRM Lead", lead_name, "lead_type")
                        update_fields = {}
                        if row.get("source_name"):
                            update_fields["source"] = row.get("source_name")
                        if row.get("source_id"):
                            update_fields["source_id"] = row.get("source_id")
                        if row.get("uploaded_source"):
                            update_fields["upload_source"] = row.get("uploaded_source")
                        if row.get("uploaded_at"):
                            update_fields["lead_uploaded_at"] = datetime.datetime.strptime(
                                row.get("uploaded_at"),
                                "%d-%m-%Y %H:%M",
                            )
                        if lead_type != EnumValues.LeadType.DRIVER:
                            if row.get("status_id"):
                                update_fields["status"] = row.get("status_id")
                            if row.get("primary_status"):
                                update_fields["primary_status"] = row.get("primary_status")
                            if row.get("secondary_status"):
                                update_fields["secondary_status"] = row.get("secondary_status")
                        if update_fields:
                            frappe.db.set_value(
                                "CRM Lead",
                                lead_name,
                                update_fields,
                                update_modified=True,
                            )
                        updated += 1
                        batch_updated += 1
                        _mark_raw_row(mobile_no, is_processed=1)
                        processed += 1
                        batch_processed += 1
                        frappe.db.commit()
                    else:
                        lead_id = get_next_lead_id()["lead_id"]
                        pending_new_leads.append(_build_new_lead_values(row, lead_id, now()))
                except Exception as exc:
                    failed += 1
                    batch_failed += 1
                    frappe.db.rollback()
                    _mark_raw_row(mobile_no, is_processed=1, error=str(exc)[:500])
                    logger.exception("Raw lead import failed for mobile_no=%s", mobile_no)
                    frappe.db.commit()

        if pending_new_leads:
            try:
                _bulk_insert_new_leads(pending_new_leads)
                for lead in pending_new_leads:
                    _mark_raw_row(lead["mobile_no"], is_processed=1)
                batch_created = len(pending_new_leads)
                created += batch_created
                batch_processed += batch_created
                processed += batch_created
                frappe.db.commit()
            except Exception as exc:
                frappe.db.rollback()
                error = str(exc)[:500]
                for lead in pending_new_leads:
                    _mark_raw_row(lead["mobile_no"], is_processed=1, error=error)
                batch_failed = len(pending_new_leads)
                failed += batch_failed
                logger.exception("Raw lead bulk insert failed")
                frappe.db.commit()

        batch_elapsed = time.monotonic() - batch_started_at
        total_elapsed = time.monotonic() - started_at
        logger.info(
            "Raw lead import batch: batch_size=%s batch_processed=%s batch_created=%s batch_updated=%s batch_failed=%s "
            "total_processed=%s total_created=%s total_updated=%s total_failed=%s "
            "batch_elapsed_seconds=%.2f batch_rows_per_second=%s total_elapsed_seconds=%.2f total_rows_per_second=%s",
            len(rows),
            batch_processed,
            batch_created,
            batch_updated,
            batch_failed,
            processed,
            created,
            
            updated,
            failed,
            batch_elapsed,
            round(batch_processed / batch_elapsed, 2) if batch_elapsed else batch_processed,
            total_elapsed,
            round(processed / total_elapsed, 2) if total_elapsed else processed,
        )

    total_elapsed = time.monotonic() - started_at
    logger.info(
        "Raw lead import finished: processed=%s created=%s updated=%s failed=%s elapsed_seconds=%.2f rows_per_second=%s",
        processed,
        created,
        updated,
        failed,
        total_elapsed,
        round(processed / total_elapsed, 2) if total_elapsed else processed,
    )
    return {
        "processed": processed,
        "created": created,
        "updated": updated,
        "failed": failed,
    }
