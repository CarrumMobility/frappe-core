from datetime import datetime, timedelta
from frappe.utils import flt, get_datetime, get_time, getdate
import frappe

class UtilService:
    def __init__(self):
        pass

    def get_lead_status_to_update(self, currentPrimaryStatus: str, currentSecondaryStatus: str, newPrimaryStatus: str, newSecondaryStatus: str):
        if currentPrimaryStatus != "NEW" and newPrimaryStatus == "NEW":
            return {
                "primary_status": currentPrimaryStatus,
                "secondary_status": currentSecondaryStatus,
            }

        if currentPrimaryStatus == "CONVERTED":
            return {
                "primary_status": currentPrimaryStatus,
                "secondary_status": currentSecondaryStatus,
            }
            
        return {
            "primary_status": newPrimaryStatus,
            "secondary_status": newSecondaryStatus,
        }


    def create_event_for_callback(
        self,
        lead_id,
        call_session_id: str,
        callback_datetime,
        callback_comments: str,
        remind_before_minutes: int,
        expected_call_duration_minutes: int,
    ):
        call_at = get_datetime(callback_datetime)
        if not call_at:
            frappe.throw(
                frappe._("Invalid callback date and time"),
                title=frappe._("Callback"),
            )

        remind_m = int(remind_before_minutes or 0)
        duration_m = int(expected_call_duration_minutes or 5)
        if duration_m < 1:
            duration_m = 5

        starts_on = call_at - timedelta(minutes=remind_m)
        ends_on = call_at + timedelta(minutes=duration_m)

        event_doc = frappe.new_doc("Event")

        event_doc.set("subject", f"{lead_id}: Callback Scheduled")
        event_doc.set("event_category", "Callback")
        event_doc.set("event_type", "Private")
        event_doc.set("status", "Open")
        event_doc.set("starts_on", starts_on)
        event_doc.set("call_at", call_at)
        event_doc.set("ends_on", ends_on)
        event_doc.set("reference_doctype", "CRM Lead")
        event_doc.set("reference_docname", lead_id)
        event_doc.set("reference_call_session", call_session_id)
        event_doc.set("description", callback_comments)
        event_doc.set("callback_status", "Scheduled")

        event_doc.save(ignore_permissions=True)

        return event_doc.name
