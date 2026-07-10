import frappe

from core.constants.enums import EnumValues
from core.observability.newrelic import record_custom_event

_MAX_LEADS_PER_REQUEST = 100

@frappe.whitelist(methods=["POST"])
def track_lead_views(lead_ids, view_type="list", route_name=None):
    """Frontend → core: record which leads a user viewed."""
    if frappe.session.user == "Guest":
        return {"recorded": 0}

    leads = frappe.parse_json(lead_ids) if isinstance(lead_ids, str) else lead_ids
    if not isinstance(leads, list):
        leads = [leads]

    user = frappe.session.user
    route = (route_name or "").strip()
    view = (view_type or "list").strip()

    recorded = 0
    for lead_id in leads[:_MAX_LEADS_PER_REQUEST]:
        lead_id = str(lead_id or "").strip()
        if not lead_id:
            continue

        record_custom_event(
            EnumValues.CrmEventTypes.CrmLeadViewed,
            {
                "frappe.user": user,
                "lead_id": lead_id,
                "view_type": view,      # "list" | "detail"
                "route_name": route,    # e.g. "Leads", "Lead"
            },
        )
        recorded += 1

    return {"recorded": recorded}