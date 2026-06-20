import datetime
import logging
import time

import frappe
from frappe import _

from core.constants.enums import EnumValues
from frappe.utils.synchronization import filelock

logger = frappe.logger("core.api.csv_upload")
logger.setLevel(logging.INFO)

RAW_LEAD_TABLE = "temp_lead_raw_data"
BATCH_SIZE = 2000

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


@frappe.whitelist()
def process_lead_from_raw_to_lead_table():
    upsert_upload_key_in_redis(True)

    frappe.enqueue(
        method="core.api.csv_upload.process_lead_from_raw_to_lead_table_consumer",
        queue="long",
        timeout=60 * 60 * 24,
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

        for row in rows:
            mobile_no = (row.get("mobile_no") or "").strip()
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
                            update_fields["lead_type"] = EnumValues.LeadType.LEAD
                        if update_fields:
                            frappe.db.set_value(
                                "CRM Lead",
                                lead_name,
                                update_fields,
                                update_modified=True,
                            )
                        updated += 1
                        batch_updated += 1
                    else:
                        new_lead = frappe.new_doc("CRM Lead")
                        new_lead.mobile_no = mobile_no
                        new_lead.lead_type = EnumValues.LeadType.LEAD
                        if(row.get("source_name")):
                            new_lead.source = row.get("source_name")

                        if(row.get("source_id")):
                            new_lead.source_id = row.get("source_id")

                        if(row.get("uploaded_at")):
                            new_lead.lead_uploaded_at =datetime.datetime.strptime(
                                row.get("uploaded_at"),
                                "%d-%m-%Y %H:%M"
                            )
                        if row.get("status_id"):
                            new_lead.status = row.get("status_id")

                        if row.get("primary_status"):
                            new_lead.primary_status = row.get("primary_status")

                        if row.get("secondary_status"):
                            new_lead.secondary_status = row.get("secondary_status")

                        new_lead.insert(ignore_permissions=True)
                        created += 1
                        batch_created += 1

                    _mark_raw_row(mobile_no, is_processed=1)
                    processed += 1
                    batch_processed += 1
                except Exception as exc:
                    failed += 1
                    batch_failed += 1
                    frappe.db.rollback()
                    _mark_raw_row(mobile_no, is_processed=1, error=str(exc)[:500])
                    logger.exception("Raw lead import failed for mobile_no=%s", mobile_no)

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
