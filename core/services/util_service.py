from datetime import datetime, timedelta
from core.constants.enums import EnumValues
from frappe.utils import flt, get_datetime, get_time, getdate
import frappe
from frappe.core.doctype.user.user import update_password as original_update_password
from frappe.utils.data import today


def _crm_lead_event_subject(lead_id: str, suffix: str) -> str:
	"""Event subject: ``(LEAD_ID) Lead Name: (Suffix)`` — name omitted if missing."""
	lead_name = (frappe.db.get_value("CRM Lead", lead_id, "lead_name") or "").strip()
	if lead_name:
		return f"({lead_id}) {lead_name}: ({suffix})"
	return f"({lead_id}): ({suffix})"


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

        event_doc.set("subject", _crm_lead_event_subject(lead_id, "Callback scheduled"))
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

    
    def create_event_for_visit_date(
        self,
        lead_id,
        scheduled_visit_date,
        disposition_remarks=None,
        call_session_id: str | None= None,
    ):
        """Keep an Event (category Visit Date) in sync with scheduled visit on Call Session."""

        svd = (
            str(scheduled_visit_date).strip()
            if scheduled_visit_date is not None and str(scheduled_visit_date).strip()
            else ""
        )
        lead_id = (lead_id or "").strip()
        if not svd or not lead_id:
            return None

        # Scheduling a visit supersedes open Callback events still marked Scheduled.
        # if frappe.db.has_column("Event", "callback_status"):
        ev_names = frappe.get_all(
            EnumValues.ReferenceDocType.EVENT,
            filters={
                "reference_doctype": EnumValues.ReferenceDocType.CRM_LEAD,
                "reference_docname": lead_id,
                "event_category": EnumValues.EventCallbackCategory.VISIT_DATE,
                "callback_status": EnumValues.EventCallbackStatus.SCHEDULED
            },
            pluck="name",
        )
        for ev_name in ev_names:
            event_doc = frappe.get_doc(EnumValues.ReferenceDocType.EVENT, ev_name)
            event_doc.set("callback_status", EnumValues.EventCallbackStatus.OVERRIDE)
            event_doc.save(ignore_permissions=True)

        visit_d = getdate(svd)
        starts_on = get_datetime(f"{visit_d} 00:00:00")
        ends_on = starts_on + timedelta(days=1) - timedelta(seconds=1)
        remarks = (
            str(disposition_remarks).strip()
            if disposition_remarks is not None and str(disposition_remarks).strip()
            else None
        )

        event_doc = frappe.new_doc(EnumValues.ReferenceDocType.EVENT)
        event_doc.set("subject", _crm_lead_event_subject(lead_id, "Visit Scheduled"))
        event_doc.set("event_category", EnumValues.EventCallbackCategory.VISIT_DATE)
        event_doc.set("event_type", "Private")
        event_doc.set("status", "Open")
        event_doc.set("starts_on", starts_on)
        event_doc.set("call_at", starts_on)
        event_doc.set("ends_on", ends_on)
        event_doc.set("reference_doctype", EnumValues.ReferenceDocType.CRM_LEAD)
        event_doc.set("reference_docname", lead_id)
        event_doc.set("callback_status", EnumValues.EventCallbackStatus.SCHEDULED)
    
        if call_session_id is not None:
            event_doc.set("reference_call_session", call_session_id)
        if remarks:
            event_doc.set("description", remarks)
        event_doc.save(ignore_permissions=True)
        
        return event_doc

    def mark_visit_date_events_as_completed(self, lead_id: str):
        event_names = frappe.get_all(
            EnumValues.ReferenceDocType.EVENT,
            filters={
                "reference_doctype": EnumValues.ReferenceDocType.CRM_LEAD,
                "reference_docname": lead_id,
                "event_category": EnumValues.EventCallbackCategory.VISIT_DATE,
                "callback_status": EnumValues.EventCallbackStatus.SCHEDULED,
                "start_on": ("<", get_datetime(today())),
            },
            pluck="name",
        )

        for event_name in event_names or []:
            event_doc = frappe.get_doc(EnumValues.ReferenceDocType.EVENT, event_name)
            event_doc.set("callback_status", EnumValues.EventCallbackStatus.COMPLETED)
            event_doc.save(ignore_permissions=True)

    def block_desk_access(self):
        if frappe.session.user == "Administrator":
            return

        if frappe.session.user == "Guest":
            return

        path = frappe.request.path or ""

        if path.startswith("/app"):
            frappe.throw(frappe._("Desk access is disabled"), title=frappe._("Permission Error"))

    def block_password_change(*args, **kwargs):
        user_doc= frappe.get_doc('User', frappe.session.user)
        userRoleDetails = user_doc.roles

        for roleDetail in userRoleDetails:
            roleName = roleDetail.role
            if roleName == EnumValues.Roles.SYSTEM_USER:
                return original_update_password(*args, **kwargs)

        frappe.throw(frappe._("Password change is disabled"), title=frappe._("Permission Error"))


util_service = UtilService()
blockDeskAccess = util_service.block_desk_access

@frappe.whitelist()
def blockPasswordChange(*args, **kwargs):
    util_service = UtilService()
    return util_service.block_password_change(*args, **kwargs)