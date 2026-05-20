from datetime import datetime, timedelta
from core.constants.enums import EnumValues
from frappe.utils import get_datetime, getdate, now_datetime
import frappe
import requests
from frappe.core.doctype.user.user import update_password as original_update_password
from frappe.utils.data import today

def _apply_crm_lead_snapshot_to_event(event_doc, lead_id: str) -> None:
	"""Set ``crm_lead_name`` and ``preferred_scheme`` from CRM Lead (custom Event fields)."""
	lead_id = (lead_id or "").strip()
	if not lead_id or not frappe.db.exists("CRM Lead", lead_id):
		return
	row = frappe.db.get_value(
		"CRM Lead",
		lead_id,
		["lead_name", "preferred_scheme"],
		as_dict=True,
	)
	if not row:
		return
	ln = (row.get("lead_name") or "").strip()
	ps = (row.get("preferred_scheme") or "").strip()
	if ln:
		event_doc.set("crm_lead_name", ln)
	if ps:
		event_doc.set("preferred_scheme", ps)


class UtilService:
    def __init__(self):
        pass

    def crm_lead_event_subject(self,lead_id: str, suffix: str) -> str:
        """Event subject: ``(LEAD_ID) Lead Name: (Suffix)`` — name omitted if missing."""
        lead_name = (frappe.db.get_value("CRM Lead", lead_id, "lead_name") or "").strip()
        if lead_name:
            return f"({lead_id}) {lead_name}: ({suffix})"
        return f"({lead_id}): ({suffix})"

    def create_event_for_callback(
        self,
        lead_id,
        call_session_id: str,
        callback_datetime,
        callback_comments: str,
        remind_before_minutes: int,
        expected_call_duration_minutes: int,
        disposition_status: str | None = None,
        sub_disposition_status: str | None = None,
        disposition_remarks: str | None = None,
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

        event_doc.set("subject", self.crm_lead_event_subject(lead_id, "Callback scheduled"))
        event_doc.set("event_category", EnumValues.EventCallbackCategory.CALLBACK)
        event_doc.set("event_type", "Private")
        event_doc.set("status", "Open")
        event_doc.set("starts_on", starts_on)
        event_doc.set("call_at", call_at)
        event_doc.set("ends_on", ends_on)
        event_doc.set("reference_doctype", EnumValues.ReferenceDocType.CRM_LEAD)
        event_doc.set("reference_docname", lead_id)
        event_doc.set("reference_call_session", call_session_id)
        event_doc.set("description", callback_comments)
        event_doc.set("callback_status", EnumValues.EventCallbackStatus.SCHEDULED)

        _apply_crm_lead_snapshot_to_event(event_doc, lead_id)
        dr = (
            str(disposition_remarks).strip()
            if disposition_remarks is not None and str(disposition_remarks).strip()
            else ""
        )
        cc = (
            str(callback_comments).strip()
            if callback_comments is not None and str(callback_comments).strip()
            else ""
        )
        ev_rmk = dr or cc
        if ev_rmk:
            event_doc.set("disposition_remarks", ev_rmk)

        ds = (disposition_status or "").strip() if disposition_status is not None else ""
        sub = (
            (sub_disposition_status or "").strip()
            if sub_disposition_status is not None
            else ""
        )
        if ds:
            event_doc.set("disposition_status", ds)
        if sub:
            event_doc.set("sub_disposition_status", sub)

        event_doc.save(ignore_permissions=True)

        return event_doc.name

    
    def create_event_for_visit_date(
        self,
        lead_id,
        scheduled_visit_date,
        disposition_remarks=None,
        call_session_id: str | None= None,
        disposition_status: str | None = None,
        sub_disposition_status: str | None = None
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

        visit_dt = get_datetime(svd)
        if not visit_dt:
            frappe.throw(
                frappe._("Invalid scheduled visit date or time"),
                title=frappe._("Visit"),
            )
        # ``YYYY-MM-DD`` only: keep legacy all-day visit window on the calendar.
        t = svd.strip()
        is_date_only = (
            len(t) == 10
            and t[4:5] == "-"
            and t[7:8] == "-"
            and " " not in t
            and "t" not in t.lower()
        )
        if is_date_only:
            visit_d = getdate(svd)
            starts_on = get_datetime(f"{visit_d} 00:00:00")
            ends_on = starts_on + timedelta(days=1) - timedelta(seconds=1)
            call_at = starts_on
        else:
            call_at = visit_dt
            starts_on = visit_dt
            ends_on = visit_dt + timedelta(hours=1)
        remarks = (
            str(disposition_remarks).strip()
            if disposition_remarks is not None and str(disposition_remarks).strip()
            else None
        )

        event_doc = frappe.new_doc(EnumValues.ReferenceDocType.EVENT)
        event_doc.set("subject", self.crm_lead_event_subject(lead_id, "Visit Scheduled"))
        event_doc.set("event_category", EnumValues.EventCallbackCategory.VISIT_DATE)
        event_doc.set("event_type", "Private")
        event_doc.set("status", "Open")
        event_doc.set("starts_on", starts_on)
        event_doc.set("call_at", call_at)
        event_doc.set("ends_on", ends_on)
        event_doc.set("reference_doctype", EnumValues.ReferenceDocType.CRM_LEAD)
        event_doc.set("reference_docname", lead_id)
        event_doc.set("callback_status", EnumValues.EventCallbackStatus.SCHEDULED)

        ds = (disposition_status or "").strip() if disposition_status is not None else ""
        sub = (
            (sub_disposition_status or "").strip()
            if sub_disposition_status is not None
            else ""
        )
        if ds:
            event_doc.set("disposition_status", ds)
        if sub:
            event_doc.set("sub_disposition_status", sub)

        if call_session_id is not None:
            event_doc.set("reference_call_session", call_session_id)
        if remarks:
            event_doc.set("description", remarks)
            event_doc.set("disposition_remarks", remarks)
        _apply_crm_lead_snapshot_to_event(event_doc, lead_id)
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
                "starts_on": ("<=",today()),
            },
            pluck="name",
        )
        
        for event_name in event_names or []:
            event_doc = frappe.get_doc(EnumValues.ReferenceDocType.EVENT, event_name)
            event_doc.set("callback_status", EnumValues.EventCallbackStatus.COMPLETED)
            event_doc.save(ignore_permissions=True)

        return len(event_names or [])

    def create_event_for_walkin_completed(
        self,
        lead_id: str,
        *,
        disposition_status: str | None = None,
        sub_disposition_status: str | None = None,
        disposition_remarks: str | None = None,
    ) -> str | None:
        """Record a completed walk-in Visit Date event when no scheduled visit event exists."""
        lead_id = (lead_id or "").strip()
        if not lead_id:
            return None

        now_dt = get_datetime(now_datetime())
        event_doc = frappe.new_doc(EnumValues.ReferenceDocType.EVENT)
        event_doc.set("subject", self.crm_lead_event_subject(lead_id, "Walk-in"))
        event_doc.set("event_category", EnumValues.EventCallbackCategory.VISIT_DATE)
        event_doc.set("event_type", "Private")
        event_doc.set("status", "Completed")
        event_doc.set("starts_on", now_dt)
        event_doc.set("call_at", now_dt)
        event_doc.set("ends_on", now_dt)
        event_doc.set("reference_doctype", EnumValues.ReferenceDocType.CRM_LEAD)
        event_doc.set("reference_docname", lead_id)
        event_doc.set("callback_status", EnumValues.EventCallbackStatus.COMPLETED)

        ds = (disposition_status or "").strip() if disposition_status is not None else ""
        sub = (
            (sub_disposition_status or "").strip()
            if sub_disposition_status is not None
            else ""
        )
        if ds:
            event_doc.set("disposition_status", ds)
        if sub:
            event_doc.set("sub_disposition_status", sub)

        remarks = (
            str(disposition_remarks).strip()
            if disposition_remarks is not None and str(disposition_remarks).strip()
            else ""
        )
        if remarks:
            event_doc.set("description", remarks)
            event_doc.set("disposition_remarks", remarks)

        _apply_crm_lead_snapshot_to_event(event_doc, lead_id)
        event_doc.save(ignore_permissions=True)
        return event_doc.name

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

    # Closed primary buckets — once a lead is here it can only move between these.
    CLOSED_PRIMARY_STATUSES = frozenset({"Drop", "Converted"})

    def is_status_change_locked_for_tc_oa(
        self, primary_status: str, new_primary_status: str
    ) -> bool:
        """Return True when the primary-status transition must be **blocked**.

        Rule: a lead in a closed bucket (``Drop`` / ``Converted``) can only move
        between closed buckets. Any other transition is allowed.

        - Open → anything: allowed (returns ``False``).
        - Closed → closed (or unchanged): allowed (returns ``False``).
        - Closed → open (e.g. ``Drop`` → ``Interested``): blocked (returns ``True``).
        """
        cur = (primary_status or "").strip()
        new = (new_primary_status or "").strip()
        if not new or new == cur:
            return False
        if cur in self.CLOSED_PRIMARY_STATUSES and new not in self.CLOSED_PRIMARY_STATUSES:
            return True
        return False

    def un_assign_secondary_lead_from_lead(self, lead_id: str):
        """Clear ``primary_lead`` for all CRM Leads pointing at ``lead_id``."""
        if not lead_id:
            return {"cleared": 0}
        children = frappe.get_all(
            "CRM Lead",
            filters={"primary_lead": lead_id},
            pluck="name",
        )
        for name in children:
            frappe.db.set_value("CRM Lead", name, "primary_lead", None)
        return {"cleared": len(children), "names": children}

    def raise_driver_return_request(
        self,
        identification_type: str,
        request_reason: str | None = None,
        old_carrum_account_id: str | None = None,
        new_account_id: str | None = None,
        identification_key: str | None = None,
        identification_value: str | None = None,
    ):
        """POST to Carrum re-onboarding API (driver return / reactivation / duplicate identity).

        ``field_update`` matches ``POST .../management/reonboarding`` with ``identification_key``
        plus the same key as field value (e.g. ``driving_licence_number``), and ``new_account_id``.
        CRM Lead fieldnames map to API: ``driving_license_number`` → ``driving_licence_number``,
        ``aadhar_no`` → ``aadhar_number``, ``pancard_number`` → ``pancard_number``.
        """
        body: dict = {}
        crm_to_api = {
                "driving_license_number": "driving_licence_number",
                "aadhar_no": "aadhar_number",
                "pancard_number": "pancard_number",
                "driving_licence_number": "driving_licence_number",
                "aadhar_number": "aadhar_number",
                "mobile_no": "phone"
        }
        if identification_type == "reactivation":
            if not old_carrum_account_id:
                frappe.throw(frappe._("oldCarrumAccountId is required"))
            body = {
                "old_account_id": old_carrum_account_id,
                "identification_key": identification_type,
                "request_reason": request_reason or "",
            }
        elif identification_type == "field_update":
            if not new_account_id:
                frappe.throw(frappe._("new_account_id is required"))
            if not identification_value:
                frappe.throw(frappe._("identification_value is required"))
            ik = (identification_key or "").strip()
            
            api_key = crm_to_api.get(ik)
            if not api_key:
                frappe.throw(
                    frappe._("Unsupported identification_key for re-onboarding: {0}").format(
                        ik or "(empty)"
                    )
                )
            body = {
                "identification_key": api_key,
                "new_account_id": new_account_id,
                api_key: identification_value,
            }
            if request_reason:
                body["request_reason"] = request_reason
        elif identification_key == "mobile_no": 
            body = {
                "identification_key": "phone",
                "phone": identification_value,
                "request_reason": request_reason,
            }
        else:
            frappe.throw(
                frappe._("Invalid identification type: {0}").format(identification_type)
            )

        base = str(frappe.conf.get("old_carrum_base_url") or "").rstrip("/")
        if not base:
            frappe.throw(
                frappe._("Old Carrum base URL is not configured (old_carrum_base_url)")
            )

        url = f"{base}/api/v1/management/reonboarding"
        token = (frappe.conf.get("old_carrum_token") or "").strip()
        if not token:
            frappe.throw(frappe._("Old Carrum token is not configured (old_carrum_token)"))
        auth = token if token.lower().startswith("carrum ") else f"carrum {token}"
        headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "*/*"}
        response = requests.post(url, headers=headers, json=body, timeout=60)

        try:
            response_data = response.json()
        except ValueError:
            response_data = None

        if not response.ok:
            msg = response.text or str(response.status_code)
            if isinstance(response_data, dict) and response_data.get("message"):
                msg = response_data.get("message")
            frappe.throw(frappe._("Failed to raise driver return request: {0}").format(msg))

        if not response_data:
            frappe.throw(frappe._("Invalid response from driver service"))

        if response_data.get("status") == "success":
            return True

        err = (
            response_data.get("message")
            or response_data.get("error")
            or frappe._("Request was not successful")
        )
        frappe.throw(frappe._("Failed to raise driver return request: {0}").format(err))


util_service = UtilService()
blockDeskAccess = util_service.block_desk_access

@frappe.whitelist()
def blockPasswordChange(*args, **kwargs):
    util_service = UtilService()
    return util_service.block_password_change(*args, **kwargs)
