import frappe
import core.services.call_service as call_service
log = frappe.logger("core_api_call")

@frappe.whitelist(methods=['POST'])
def start_call(calling_method: str = None, leadId: str = None):
    log.info(f"Starting call with calling_method: {calling_method} and leadId: {leadId}")
    user = frappe.session.user
    data = frappe.request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    form = dict(frappe.local.form_dict or {})
    for key, val in form.items():
        if key not in data and key not in ("cmd", "csrf_token"):
            data[key] = val
    if not calling_method:
        calling_method = data.get("calling_method")
    if not leadId:
        leadId = data.get("leadId")
    manual_dial = bool(
        data.get("manual_dial")
        or data.get("manualDial")
    )
    result = call_service.start_call(
        calling_method, leadId, user, manual_dial=manual_dial
    )
    print(result)
    return result

@frappe.whitelist(methods=['POST'])
def end_call(calling_method: str, call_id: str):
    log.info(f"Ending call with calling_method: {calling_method} and call_id: {call_id}")
    user = frappe.session.user
    return call_service.end_call(calling_method, call_id, user)

@frappe.whitelist(methods=['POST'])
def submit_disposition():
    """
    Store disposition on Call Session (Click2Call and Dialer both use Call Session name).

    Body/JSON:
      call_session_id — Call Session name (Click2Call and Dialer)
      calling_method — \"Click2Call\" | \"Dialer\"
      disposition_status — selected ``custom_primary_status`` string (stored on session; not doc name)
      disposition_code — vendor code from CRM Lead Status ``custom_disposition_code`` (Smartflo body)
      disposition_remarks — optional string
      disposition_timing — optional \"IMMEDIATE\" | \"LATE\" (Call Session; default IMMEDIATE)
      sub_disposition_status (or sub_disposition) — selected row's ``lead_status`` string (not doc name)
      status_pk — optional ``CRM Lead Status`` document name (primary key) for the selected disposition row
      callback_datetime, callback_comments, remind_before_minutes,
      expected_call_duration_minutes — optional (Dialer / callbacks)
      is_visit_scheduled, scheduled_visit_date — optional (visit disposition)
    """
    data = frappe.request.get_json(silent=True) or {}
    return call_service.submit_disposition_request(data)

@frappe.whitelist(allow_guest=True)
def reconcile_active_calls():
    return call_service.reconcile_active_calls()

@frappe.whitelist(methods=["POST"], allow_guest=True)
def handle_agent_call_connected_webhook():
    payload = frappe.request.get_json() or {}
    return call_service.handle_agent_call_connected_webhook(vendor_name="Smartflo", payload=payload)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def handle_customer_call_connected_webhook():
    payload = frappe.request.get_json() or {}
    return call_service.handle_customer_call_connected_webhook(vendor_name="Smartflo", payload=payload)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def handle_call_missed_by_customer_webhook():
    payload = frappe.request.get_json() or {}
    return call_service.handle_call_missed_by_customer_webhook(vendor_name="Smartflo", payload=payload)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def handle_answered_call_hangup_webhook():
    payload = frappe.request.get_json() or {}
    return call_service.handle_answered_call_hangup_webhook(vendor_name="Smartflo", payload=payload)

@frappe.whitelist(methods=['POST'])
def start_dialer_session():
    payload = frappe.request.get_json() or {}
    return call_service.start_dialer_session(user=frappe.session.user, payload=payload)

@frappe.whitelist(methods=["POST"])
def end_dialer_session():
    payload = frappe.request.get_json() or {}
    return call_service.end_dialer_session(user=frappe.session.user,payload=payload)

@frappe.whitelist(methods=["POST"])
def toggle_dialer_break():
    payload = frappe.request.get_json() or {}
    return call_service.toggle_dialer_break(user=frappe.session.user, payload=payload)

@frappe.whitelist(methods=["POST"])
def get_dialer_break_status():
    return call_service.get_dialer_break_status(user=frappe.session.user)

@frappe.whitelist(methods=["POST"],allow_guest=True)
def dialer_call_connected_webhook():
    payload = frappe.request.get_json() or {}
    user = frappe.session.user
    log.info(f"Dialer call connected webhook payload: {payload}")
    return call_service.dialer_call_connected(user=user, payload=payload)

@frappe.whitelist(methods=['POST'], allow_guest=True)
def dialer_call_disconnected_webhook():
    payload = frappe.request.get_json() or {}
    user = frappe.session.user
    log.info(f"Dialer call disconnected webhook payload: {payload}")
    return call_service.dialer_call_disconnected(user=user, payload=payload)

@frappe.whitelist(methods=['POST'], allow_guest=True)
def dialer_call_disposed_webhook():
    payload = frappe.request.get_json() or {}
    user = frappe.session.user
    log.info(f"Dialer call disposed webhook payload: {payload}")
    return call_service.dialer_call_disposed(user=user, payload=payload)

@frappe.whitelist()
def get_last_call():
    """Latest Call Session for the current user (Dialer / Click2Call); UI shape matches LastCallStatusModal."""
    return call_service.get_last_call(user=frappe.session.user)

@frappe.whitelist(methods=["POST"])
def get_call_session_disposition_remarks():
    payload = frappe.request.get_json() or {}
    return call_service.get_call_session_disposition_remarks(
        frappe.session.user,
        payload,
    )


@frappe.whitelist(methods=["POST"])
def update_call_session():
    payload = frappe.request.get_json() or {}
    return call_service.update_call_session(payload)