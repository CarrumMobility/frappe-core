import json
import re
from datetime import datetime, timedelta
from time import sleep
from core.api.carrum_accounts import get_frappe_user_by_smartflo_account, get_smartflo_credentials_for_frappe_user
from crm.api.event import enqueue_complete_today_callback_followups_for_lead
from crm.api.lead import update_lead_from_call_disposition
from crm.utils import parse_phone_number
import frappe
import core.integrations.smartflo.client as smartflo_client
from frappe.exceptions import DoesNotExistError
from frappe.utils import flt, get_datetime, get_time, getdate
from core.services.util_service import UtilService
log = frappe.logger("core.services.call_service")

util_service = UtilService()
default_telephony_vendor = "Smartflo"


def _enqueue_apply_not_connected_dial_for_today_lead_callback(
    lead_name: str, lock_key: str | None = None
) -> None:
    """
    Defer not-connected dial side effects to the default RQ worker (same target as
    crm.api.event.apply_not_connected_dial_for_today_lead_callback) without importing
    a separate enqueue symbol from crm.api.event.
    """
    if not (lead_name or "").strip():
        return
    try:
        frappe.enqueue(
            "crm.api.event.apply_not_connected_dial_for_today_lead_callback",
            queue="default",
            enqueue_after_commit=True,
            lead_name=lead_name.strip(),
            lock_key=lock_key,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "_enqueue_apply_not_connected_dial_for_today_lead_callback",
        )


def _set_lead_telecaller(lead_id: str | None, agent: str | None) -> None:
    """Set ``CRM Lead.telecaller`` to the disposing agent.

    Goes through ``lead.save`` (not ``frappe.db.set_value``) so the CRM Lead controller
    hook fires and re-assigns the lead's WhatsApp conversation in Chatwoot to the new
    telecaller. Idempotent: skips when the telecaller is unchanged. Silent on failure.
    """
    log.info(f"Setting lead telecaller on dispose with lead_id: {lead_id} and agent: {agent}")
    if not lead_id or not agent:
        log.info(f"Skipping set_lead_telecaller_on_dispose with lead_id: {lead_id} and agent: {agent}")
        return
    agent = agent.strip()
    if not agent or agent in ("Guest", "Administrator"):
        return
    try:
        if not frappe.db.exists("User", agent):
            return
        current = (frappe.db.get_value("CRM Lead", lead_id, "telecaller") or "").strip()
        if current == agent:
            return
        lead = frappe.get_doc("CRM Lead", lead_id)
        lead.telecaller = agent
        lead.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "set_lead_telecaller_on_dispose")


def _webhook_acquire_lock(key_suffix: str, ttl: int = 60) -> bool:
    """Best-effort distributed lock; returns True if caller should proceed."""
    try:
        cache = frappe.cache()
        k = cache.make_key(f"smartflo_webhook:{key_suffix}")
        acquired = cache.set(k, "1", nx=True, ex=ttl)
        return acquired is not False and acquired is not None
    except Exception:
        return True


def _hangup_at_from_smartflo_payload(payload: dict):
    raw = (payload.get("end_stamp") or "").strip()
    if raw:
        dt = get_datetime(raw)
        if dt:
            return dt
    return frappe.utils.now_datetime()


def _lead_last_call_datetime_from_db(lead_id: str):
    last_date, last_time = frappe.db.get_value(
        "CRM Lead", lead_id, ["last_call_date", "last_call_time"]
    )
    if not last_date:
        return None
    if last_time is None or last_time == "":
        return get_datetime(str(last_date))
    if isinstance(last_time, timedelta):
        last_time = (datetime.min + last_time).time()
    return get_datetime(f"{last_date} {last_time}")


def _call_session_lead_fields(call_session_record):
    lead_id = call_session_record.get("lead")
    if not lead_id:
        return None, None, None
    row = frappe.db.get_value("CRM Lead", lead_id, ["lead_name", "mobile_no"])
    if not row:
        return lead_id, None, None
    lead_name, mobile_no = row
    return lead_id, lead_name, mobile_no


_CALL_SESSION_UI_ON_CALL = frozenset(
    {"INITIATED", "AGENT_CONNECTED", "CUSTOMER_CONNECTED"},
)


def _duration_seconds_from_value(duration_val):
    if duration_val is None:
        return None
    if hasattr(duration_val, "total_seconds"):
        return int(duration_val.total_seconds())
    try:
        return int(duration_val)
    except (TypeError, ValueError):
        return None


def _call_session_status_to_ui_bucket(status: str | None) -> str:
    s = (status or "").strip().upper()
    if s == "DISPOSED":
        return "disposed"
    if s in ("DISCONNECTED", "MISSED", "FAILED"):
        return "disconnected"
    if s in _CALL_SESSION_UI_ON_CALL:
        return "on_call"
    return "other"


def _call_session_direction_to_ui(direction: str | None) -> str:
    d = (direction or "").strip().upper()
    if d == "INBOUND":
        return "Incoming"
    if d == "OUTBOUND":
        return "Outgoing"
    return (direction or "").strip()


def _direction_inbound_outbound_from_vendor_payload(payload: dict | None) -> str:
    """
    Map Smartflo/vendor ``direction`` to Call Session INBOUND | OUTBOUND.
    click_to_call / clicktocall / CTC = agent dials customer => OUTBOUND.
    """
    if not payload:
        return "OUTBOUND"
    raw = (payload.get("direction") or "").strip()
    if not raw:
        return "OUTBOUND"
    u = raw.upper()
    if u in ("INBOUND", "INCOMING"):
        return "INBOUND"
    if u in ("OUTBOUND", "OUTGOING"):
        return "OUTBOUND"
    if u == "DIALER (OUTBOUND)":
        return "OUTBOUND"
    if u in ("DIALER (INBOUND)", "DIALER (INCOMING)"):
        return "INBOUND"
    s = raw.lower()
    if "inbound" in s or "incoming" in s:
        return "INBOUND"
    return "OUTBOUND"


class CallService:
    def __init__(self):
        pass

    AGENT_DIALER_SESSION_LOG_DOCTYPE = "User dialer session logs"
    SESSION_BREAK_LOG_DOCTYPE = "User dialer session break logs"

    def start_call(
        self,
        calling_method: str,
        leadId: str,
        user: str,
        *,
        manual_dial: bool = False,
    ):
        log.info(f"Starting call with calling_method: {calling_method} and leadId: {leadId} and user: {user} and manual_dial: {manual_dial}")
        if calling_method == "Dialer":
            raise ValueError(f"Dialer calling method is not supported: {calling_method}")
        if calling_method != "Click2Call":
            raise ValueError(f"Invalid calling method: {calling_method}")

        if self._user_has_active_dialer_session(user):
            raise ValueError(
                frappe._(
                    "You have an active dialer session. End the session before using click-to-call."
                )
            )

        lead = frappe.get_doc("CRM Lead", leadId)
        if not lead:
            raise ValueError(f"Lead not found: {leadId}")

        mobile_no = lead.mobile_no
        if not mobile_no:
            raise ValueError(f"Mobile number not found for lead: {leadId}")

        pre_vendor_check_result = self._handle_pre_vendor_check(user)
        if pre_vendor_check_result["is_valid"] == False:
            raise ValueError(f"Pre vendor check failed: {pre_vendor_check_result['invalid_reason']}")

        call_session_doc = frappe.get_doc({
            "doctype": "Call Session",
            "lead": lead.name,
            "agent": user,
            "lead_phone": mobile_no,
            "status": "INITIATED",
            "direction": "OUTBOUND",
            "calling_method": calling_method,
            "vendor_name": default_telephony_vendor,
        })
        call_session_doc.insert()

        call_initiated_result = self._handle_click2call_start_logic(
            user,
            call_session_doc.name,
            mobile_no,
            pre_vendor_check_result["calling_config"],
            manual_dial=bool(manual_dial),
        )

        if call_initiated_result["is_valid"] == False:
            # update call session status to failed with reason
            call_session_doc.db_set("status", "FAILED")
            call_session_doc.db_set("failure_reason", call_initiated_result["reason"])
            raise ValueError(f"Call initiation failed: {call_initiated_result['reason']}")

        frappe.publish_realtime(
            event="call_initiated",
            message={
                "call_session_id": call_session_doc.name,
                "lead_id": leadId,
                "lead_name": lead.lead_name,
                "phone_number": mobile_no,
                "to_number": mobile_no,
                "calling_method": "Click2Call",
                "status": "CALL INITIATED TO AGENT",
                "after_commit": True,
                "direction": _call_session_direction_to_ui(
                    call_session_doc.get("direction") or "OUTBOUND"
                ),
            },
            user=frappe.session.user,
        )

        return {
            "status": "success",
            "call_session_id": call_session_doc.name,
            "direction": _call_session_direction_to_ui(
                call_session_doc.get("direction") or "OUTBOUND"
            ),
        }

    def end_call(self,calling_method: str, call_session_id: str, user: str):
        log.info(f"Ending call with calling_method: {calling_method} and call_session_id: {call_session_id} and user: {user}")
        if calling_method == "Click2Call":
            return self._handle_click2call_end_logic(call_session_id, user)
        elif calling_method == "Dialer":
            return self._handle_dialer_end_logic(call_session_id, user)
        else:
            raise ValueError(f"Invalid calling method: {calling_method}")

    def _resolve_dialer_call_session_name(self, call_ref: str, user: str) -> str:
        """Return Call Session name from session id or Smartflo ``agent_call_id``."""
        key = (call_ref or "").strip()
        if not key:
            raise ValueError(frappe._("Call id is required"))
        if frappe.db.exists("Call Session", key):
            return key
        filters = {"agent_call_id": key}
        if user and user != "Guest":
            names = frappe.get_all(
                "Call Session",
                filters={**filters, "agent": user},
                order_by="modified desc",
                limit_page_length=1,
                pluck="name",
            )
            if names:
                return names[0]
        names = frappe.get_all(
            "Call Session",
            filters=filters,
            order_by="modified desc",
            limit_page_length=1,
            pluck="name",
        )
        if names:
            return names[0]
        raise ValueError(frappe._("Call Session not found for {0}").format(key))

    def _handle_dialer_end_logic(self, call_session_id: str, user: str):
        session_name = self._resolve_dialer_call_session_name(call_session_id, user)
        call_session_doc = frappe.get_doc("Call Session", session_name)
        call_id = call_session_doc.agent_call_id
        smartflo_client.handle_dialer_hangup_api(user=user, call_session_id=call_id)

        return {
            "is_valid": True,
            "reason": None,
            "direction": _call_session_direction_to_ui(
                call_session_doc.get("direction")
            ),
        }


    def reconcile_active_calls(self):
        self._mark_initiated_stale_calls_as_failed()
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_reconcile_active_calls()
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

   
    def _mark_initiated_stale_calls_as_failed(self, call_session_id: str | None = None):
        now = frappe.utils.now_datetime()
        thirty_seconds_ago = now - timedelta(seconds=30)
        if not call_session_id:
            filters = {"status": "INITIATED", "creation": ("<", thirty_seconds_ago)}
        else:
            filters = {"name": call_session_id}
        call_sessions = frappe.db.get_list("Call Session", filters=filters, limit=100)
        print("======call_sessions: " + str(call_sessions))
        for call_session in call_sessions:
            print("======call_session: " + str(call_session))
            try:
                call_session_doc = frappe.get_doc("Call Session", call_session.name, ['name', 'lead', 'lead_id', 'lead_phone', 'agent'])
            except DoesNotExistError:
                continue

            print("======call_session_doc: " + str(call_session_doc.as_dict()))
            target_user = call_session_doc.get("agent")
            call_session_doc.status = "FAILED"
            call_session_doc.failure_reason = "Not answered by Agent in 30 seconds"
            call_session_doc.save(ignore_permissions=True)
            frappe.publish_realtime(
                event="call_failed",
                message={
                    "call_session_id": call_session_doc.name,
                    "lead_id": call_session_doc.lead,
                    "phone_number": call_session_doc.get("lead_phone"),
                    "failure_reason": call_session_doc.failure_reason or "",
                    "calling_method": "Click2Call",
                    "direction": _call_session_direction_to_ui(
                        call_session_doc.get("direction") or "OUTBOUND"
                    ),
                },
                user=target_user,
            )
            frappe.db.commit()



        return {
            "is_valid": True,
            "reason": None,
        }

    def _handle_smartflo_reconcile_active_calls(self):
        response = smartflo_client.handle_get_live_call_detail_api()

        return {
            "is_valid": True,
            "reason": None,
            "data": response
        }

    def _handle_click2call_end_logic(self, call_session_id: str, user):
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_click2call_end_logic(call_session_id, user)
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

    def _handle_smartflo_click2call_end_logic(self, call_session_id: str, user):
        call_session_doc = frappe.get_doc("Call Session", call_session_id)
        agent_call_id = (call_session_doc.agent_call_id or "").strip()
        if not agent_call_id:
            raise ValueError(f"Agent call ID not found for call session: {call_session_id}")

        max_retry_count = 3
        current_retry_count = 0
        is_api_end_call_success = False
        while max_retry_count > current_retry_count:
            response = smartflo_client.handle_click2call_end_api(
                user=user,
                telephony_call_id=agent_call_id,
            )
            try:
                if (
                    response.get("ok") is True
                    or response.get("Success") is True
                    or response.get("success") is True
                ):
                    is_api_end_call_success = True
                    break
                current_retry_count += 1
                continue
            except Exception as e:
                error_message = str(e)
                current_retry_count+=1
                continue
        
        if not is_api_end_call_success:
            return {
                "is_valid": False,
                "reason": "Failed to end call"
            }

        return {
            "is_valid": True,
            "reason": None,
            "direction": _call_session_direction_to_ui(
                call_session_doc.get("direction") or "OUTBOUND"
            ),
        }

    def _handle_click2call_start_logic(
        self,
        user: str,
        call_session_id: str,
        mobile_no,
        calling_config: dict,
        *,
        manual_dial: bool = False,
    ):
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_click2call_start_logic(
                    user, call_session_id, mobile_no, calling_config, manual_dial=manual_dial
                )
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

    
    def _handle_smartflo_click2call_start_logic(
        self,
        user: str,
        call_session_id: str,
        mobile_no,
        calling_config: dict,
        *,
        manual_dial: bool = False,
    ):
        # campaign_id = calling_config["default_campaign_id"]

        # max_login_retry_count = 2
        # is_logged_in = False
        # last_login_error_message = None

        # for attempt in range(max_login_retry_count):
        #     try:
        #         result = smartflo_client.handle_login_session_api(
        #             user=user, campaign_id=campaign_id
        #         )
        #         if result.get("is_valid"):
        #             is_logged_in = True
        #             break
        #         last_login_error_message = result.get("reason") or "Session login failed"

        #     except Exception as e:
        #         err = str(e)
        #         if "already logged in" in err.lower():
        #             is_logged_in = True
        #             break
        #         last_login_error_message = err

        #     sleep(2)

        # if not is_logged_in:
        #     return {
        #         "is_valid": False,
        #         "step": "login",
        #         "reason": last_login_error_message,
        #     }

        max_dial_retry_count = 2
        max_offline_retry = 1
        offline_retry_count = 0

        last_dial_error_message = None

        for attempt in range(max_dial_retry_count + max_offline_retry):
            try:
                extension_id = calling_config["extension_id"]
                calling_number = calling_config["calling_number"]

                smartflo_client.handle_click2call_start_api(
                    user=user,
                    agent_number=extension_id,
                    destination_number=mobile_no,
                    caller_id=calling_number,
                    custom_identifier=call_session_id,
                    use_async=not manual_dial,
                )

                return {"is_valid": True, "reason": None}

            except Exception as e:
                error_msg = str(e).lower()
                last_dial_error_message = str(e)
                if "agent is offline" in error_msg:
                    if offline_retry_count >= max_offline_retry:
                        break

                    offline_retry_count += 1

                    # try:
                    #     smartflo_client.handle_logout(
                    #         user=user, campaign_id=campaign_id
                    #     )
                    # except Exception:
                    #     pass

                    # sleep(0.5)

                    # try:
                    #     smartflo_client.handle_login_session_api(
                    #         user=user, campaign_id=campaign_id
                    #     )
                    # except Exception:
                    #     pass

                    sleep(0.5)
                    continue

                if attempt >= max_dial_retry_count - 1:
                    break

                sleep(0.5)

        return {
            "is_valid": False,
            "step": "dial",
            "reason": last_dial_error_message or "Failed to start click2call",
        }
    
    def _handle_pre_vendor_check(self, user: str):
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_pre_vendor_check(user)
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

    def _handle_smartflo_pre_vendor_check(self, user: str):
        smartflo_credentials = get_smartflo_credentials_for_frappe_user(user)
        is_valid = False
        invalid_reason = None
        try:
            if not smartflo_credentials:
                raise ValueError(f"Smartflo credentials not found for user: {user}")

            calling_number = (smartflo_credentials.get("callingNumber") or "").strip()
            extension_id = smartflo_credentials.get("extensionId")
            default_campaign_id = smartflo_credentials.get("defaultCampaignId")

            if not calling_number:
                raise ValueError(f"Calling number not found for user: {user}")

            if not extension_id:
                raise ValueError(f"Extension ID not found for user: {user}")

            if not default_campaign_id:
                raise ValueError(f"Default campaign ID not found for user: {user}")

            is_valid = True
        except Exception as e:
            is_valid = False
            invalid_reason = str(e)
        return {
            "is_valid": is_valid,
            "invalid_reason": invalid_reason,
            "calling_config": {
                "calling_number": calling_number,
                "extension_id": extension_id,
                "default_campaign_id": default_campaign_id
            },
        }

    def handle_agent_call_connected_webhook(self, vendor_name: str, payload: dict):
        match vendor_name:
            case "Smartflo":
                return self._handle_smartflo_agent_call_connected_webhook(payload)
            case _:
                raise ValueError(f"Invalid telephony vendor: {vendor_name}")

    def _handle_smartflo_agent_call_connected_webhook(self, payload: dict):
        '''
        {
            "uuid":"69d75426f0a9f",
            "call_to_number":"918287842425",
            "caller_id_number":"+919240202904",
            "start_stamp":"2026-04-09 12:54:21",
            "answer_agent_number":"+918287842425",
            "call_id":"1775719461.306731",
            "billing_circle":{
                "operator":"Reliance Mobile GSM",
                "circle":"Delhi"
            },
            "call_status":"Answered by agent",
            "direction":"click_to_call",
            "customer_no_with_prefix ":"918287842425",
            "ref_id":""
        }
        '''
        call_id = payload.get("call_id") or payload.get("agent_call_id")
        start_stamp = payload.get("start_stamp")
        agent_answer_event_id = payload.get("uuid")
        call_record_id = payload.get("custom_identifier")

        if not call_record_id:
            return {"is_valid": False, "reason": "missing custom_identifier"}

        lock_suffix = f"agent_connected:{call_id or agent_answer_event_id or call_record_id}"
        if not _webhook_acquire_lock(lock_suffix):
            return {"is_valid": False, "reason": "Already processing the record"}

        try:
            call_session_record = frappe.get_doc("Call Session", call_record_id)
        except DoesNotExistError:
            return {"is_valid": False, "reason": "Call session record not found"}

        try:
            if (
                call_session_record.get("agent_call_id")
                and call_session_record.get("agent_call_id") == call_id
                and call_session_record.get("status") == "AGENT_CONNECTED"
            ):
                return {"is_valid": True, "reason": None}

            call_session_record.set("agent_answered_at", start_stamp)
            call_session_record.set("status", "AGENT_CONNECTED")
            call_session_record.set("agent_call_id", call_id)
            call_session_record.set("agent_answer_event_id", agent_answer_event_id)
            call_session_record.set("agent_answer_event_log", payload)
            call_session_record.set(
                "direction",
                _direction_inbound_outbound_from_vendor_payload(payload),
            )
            call_session_record.save(ignore_permissions=True)

            lead_id, lead_name, mobile_no = _call_session_lead_fields(call_session_record)
            phone_display = (call_session_record.get("lead_phone") or mobile_no or "").strip()
            frappe.publish_realtime(
                event="call_agent_connected",
                message={
                    "call_session_id": call_session_record.name,
                    "lead_id": lead_id,
                    "lead_name": lead_name,
                    "timestamp": start_stamp,
                    "phone_number": phone_display,
                    "to_number": phone_display,
                    "status": "AGENT CONNECTED",
                    "calling_method": "Click2Call",
                    "direction": _call_session_direction_to_ui(
                        call_session_record.get("direction")
                    ),
                },
                user=call_session_record.get("agent"),
            )
            frappe.db.commit()

            return {"is_valid": True, "reason": None}
        except Exception as e:
            return {"is_valid": False, "reason": str(e)}

    def handle_customer_call_connected_webhook(self, vendor_name: str, payload: dict):
        match vendor_name:
            case "Smartflo":
                return self._handle_smartflo_customer_call_connected_webhook(payload)
            case _:
                raise ValueError(f"Invalid telephony vendor: {vendor_name}")

    def _handle_smartflo_customer_call_connected_webhook(self, payload: dict):
        '''
            {
                "answered_agent_number": {
                    "follow_me_number": "+918287842425",
                    "id": "0507297260059",
                    "name": "Kapil"
                },
                "billing_circle": {
                    "circle": "Delhi",
                    "operator": "Reliance Mobile GSM"
                },
                "call_status": "Answered by customer",
                "call_to_number": "918287842425",
                "caller_id_number": "+919240202904",
                "customer_no_with_prefix ": "918287842425",
                "customer_ring_time": "16",
                "direction": "click_to_call",
                "ref_id": "",
                "start_stamp": "2026-04-09 12:52:49",
                "uuid": "69d753c963a5d"
            }
        '''
        call_record_id = payload.get("custom_identifier")
        if not call_record_id:
            return {"is_valid": False, "reason": "missing custom_identifier"}

        try:
            call_session_record = frappe.get_doc("Call Session", call_record_id)
        except DoesNotExistError:
            return {"is_valid": False, "reason": "Call session record not found"}

        call_session_record.set("status", "CUSTOMER_CONNECTED")
        start_stamp = payload.get("start_stamp")
        lead_answer_event_id = payload.get("uuid")
        call_session_record.set("lead_answered_at", start_stamp)
        call_session_record.set("lead_answer_event_log", payload)
        call_session_record.set("lead_answer_event_id", lead_answer_event_id)
        call_session_record.set(
            "direction",
            _direction_inbound_outbound_from_vendor_payload(payload),
        )
        call_session_record.save(ignore_permissions=True)

        direction_u = (call_session_record.get("direction") or "").strip().upper()
        lead_fu = (call_session_record.get("lead") or "").strip()
        if direction_u == "OUTBOUND" and lead_fu:
            enqueue_complete_today_callback_followups_for_lead(lead_fu)

        target_user = call_session_record.get("agent")
        lead_id, lead_name, mobile_no = _call_session_lead_fields(call_session_record)
        phone_display = (call_session_record.get("lead_phone") or mobile_no or "").strip()

        frappe.publish_realtime(
            event="call_customer_connected",
            message={
                "call_session_id": call_session_record.name,
                "lead_id": lead_id,
                "lead_name": lead_name,
                "phone_number": phone_display,
                "to_number": phone_display,
                "timestamp": start_stamp,
                "status": "CUSTOMER CONNECTED",
                "calling_method": "Click2Call",
                "direction": _call_session_direction_to_ui(
                    call_session_record.get("direction")
                ),
            },
            user=target_user,
            after_commit=True
        )

        frappe.db.commit()
        return {
            "is_valid": True,
            "reason": None
        }

    def handle_call_missed_by_customer_webhook(self, vendor_name: str, payload: dict):
        match vendor_name:
            case "Smartflo":
                return self._handle_smartflo_call_missed_by_customer(payload)
            case _:
                raise ValueError(f"Invalid telephony vendor: {vendor_name}")

    def _handle_smartflo_call_missed_by_customer(self, payload: dict):
        '''
           {
                "uuid": "69d75426f0a9f",
                "call_to_number": "918287842425",
                "caller_id_number": "9240202904",
                "start_stamp": "2026-04-09 12:54:22",
                "answer_stamp": "2026-04-09 12:54:23",
                "end_stamp": "2026-04-09 12:54:53",
                "billsec": "30",
                "digits_dialed": "",
                "direction": "clicktocall",
                "duration": "30",
                "answered_agent": {
                    "id": "0507297260059",
                    "name": "Kapil-Extension",
                    "dialst": "Dialed",
                    "number": "0607297260058",
                    "agent_number": "+918287842425"
                },
                "answered_agent_name": "Kapil-Extension",
                "answered_agent_number": "0607297260058",
                "missed_agent": "",
                "call_flow": [
                    {
                    "type": "init",
                    "value": "1775719461.306731",
                    "time": "1775719462"
                    },
                    {
                    "type": "Agent",
                    "id": "0507297260059",
                    "name": "Kapil-Extension",
                    "dialst": "Dialed",
                    "num": "+918287842425",
                    "subtype": "softphone",
                    "extension": "0607297260058",
                    "time": 1775719463
                    },
                    {
                    "type": "ClickToCall",
                    "name": "PJSIP%2F%2B08287842425%40TTNSIT-00919240251000-copy2_685bdbf548498",
                    "time": 1775719463
                    },
                    {
                    "type": "hangup",
                    "time": 1775719493
                    }
                ],
                "broadcast_lead_fields": "",
                "recording_url": "https://cloudphone.tatateleservices.com/file/recording?callId=1775719461.306731&type=rec&token=V1UzMU04RXNUM3d5QXBVSU1nbUduQWM1OWRtTDk3TGY2dGJzMVZ3TFgvRzkycitacDdsK2FhYmJuU3NGUmFLdjo6YWIxMjM0Y2Q1NnJ0eXl1dQ%3D%3D",
                "call_status": "missed",
                "call_id": "1775719461.306731",
                "outbound_sec": "0",
                "agent_ring_time": "2",
                "billing_circle": {
                    "operator": "Reliance Mobile GSM",
                    "circle": "Delhi"
                },
                "call_connected": "1",
                "aws_call_recording_identifier": "6d056ccff5baf7af1ade0b3c58aa43d4",
                "customer_no_with_prefix ": "918287842425",
                "campaign_name": "$campaign_name",
                "campaign_id": "$campaign_id",
                "customer_ring_time": "30",
                "reason_key": "noanswer",
                "hangup_cause_description": "Unspecified. No other cause codes applicable.",
                "hangup_cause_code": "0",
                "hangup_cause_key": "UNSPECIFIED",
                "ref_id": ""
            }
        '''
        call_record_id = payload.get("custom_identifier")
        if not call_record_id:
            return {"is_valid": False, "reason": "missing custom_identifier"}

        try:
            call_session_record = frappe.get_doc("Call Session", call_record_id)
        except DoesNotExistError:
            return {"is_valid": False, "reason": "Call session record not found"}

        event_id = payload.get("uuid")
        if not (call_session_record.get("direction") or "").strip():
            call_session_record.set(
                "direction",
                _direction_inbound_outbound_from_vendor_payload(payload),
            )
        direction_u = (call_session_record.get("direction") or "").strip().upper()
        call_session_record.set(
            "status",
            "NOT_CONNECTED" if direction_u == "OUTBOUND" else "MISSED",
        )
        call_session_record.set("hangup_event_log", payload)
        call_session_record.set("hangup_event_id", event_id)
        call_session_record.set("hangup_at", _hangup_at_from_smartflo_payload(payload))
        call_session_record.save(ignore_permissions=True)

        lead_for_nc = (call_session_record.get("lead") or "").strip()
        if direction_u == "OUTBOUND" and lead_for_nc:
            _enqueue_apply_not_connected_dial_for_today_lead_callback(
                lead_for_nc,
                lock_key=str(event_id or payload.get("call_id") or "").strip() or None,
            )

        target_user = call_session_record.get("agent")
        lead_id, lead_name, mobile_no = _call_session_lead_fields(call_session_record)
        phone_display = (call_session_record.get("lead_phone") or mobile_no or "").strip()

        frappe.publish_realtime(
            event="call_missed_by_customer",
            message={
                "call_session_id": call_session_record.name,
                "lead_id": lead_id,
                "lead_name": lead_name,
                "phone_number": phone_display,
                "to_number": phone_display,
                "timestamp": payload.get("start_stamp"),
                "status": "CALL MISSED BY CUSTOMER",
                "calling_method": "Click2Call",
                "direction": _call_session_direction_to_ui(
                    call_session_record.get("direction") or "OUTBOUND"
                ),
            },
            user=target_user,
            after_commit=True
        )

        frappe.db.commit()
        return {
            "is_valid": True,
            "reason": None
        }

    def handle_answered_call_hangup_webhook(self, vendor_name: str, payload: dict):
        match vendor_name:
            case "Smartflo":
                return self._handle_smartflo_call_hangup(payload)
            case _:
                raise ValueError(f"Invalid telephony vendor: {vendor_name}")

    def _handle_smartflo_call_hangup(self, payload: dict):
        """
        {
            "uuid": "69db1da04ac43",
            "call_to_number": "918287842425",
            "caller_id_number": "9240202904",
            "start_stamp": "2026-04-12 09:50:48",
            "answer_stamp": "2026-04-12 09:50:48",
            "end_stamp": "2026-04-12 09:50:59",
            "billsec": "11",
            "digits_dialed": "",
            "direction": "clicktocall",
            "duration": "11",
            "answered_agent": {
                "id": "0507297260059",
                "name": "Kapil-Extension",
                "dialst": "Dialed",
                "number": "0607297260058",
                "agent_number": "+918287842425"
            },
            "answered_agent_name": "Kapil-Extension",
            "answered_agent_number": "0607297260058",
            "missed_agent": "",
            "call_flow": [
                {
                    "type": "init",
                    "value": "1775967644.594011",
                    "time": "1775967648"
                },
                {
                    "type": "Agent",
                    "id": "0507297260059",
                    "name": "Kapil-Extension",
                    "dialst": "Dialed",
                    "num": "+918287842425",
                    "subtype": "softphone",
                    "extension": "0607297260058",
                    "time": 1775967648
                },
                {
                    "type": "ClickToCall",
                    "name": "PJSIP%2F%2B08287842425%40TTNSIT-00919240251000-copy2_685bdbf548498",
                    "time": 1775967648
                },
                {
                    "type": "Agent",
                    "id": "0507297260059",
                    "name": "Kapil",
                    "number": "+918287842425",
                    "time": 1775967652,
                    "dialst": "Answered"
                },
                {
                    "anstime": 1775967652,
                    "time": 1775967659
                },
                {
                    "type": "hangup",
                    "time": 1775967659
                }
            ],
            "broadcast_lead_fields": "",
            "recording_url": "https://cloudphone.tatateleservices.com/file/recording?callId=1775967644.594011&type=rec&token=cUFNUUduc3BDMlhaUlh2Q3VTd2pVN1dRbkp6SUoyYklhZWdrRUJ2ejRoQ0lJc3pLbnUyQnNTNG5MVG9CbzdURzo6YWIxMjM0Y2Q1NnJ0eXl1dQ%3D%3D",
            "recording_name": "$recording_name",
            "call_status": "answered",
            "call_id": "1775967644.594011",
            "outbound_sec": "7",
            "agent_ring_time": "4",
            "agent_transfer_ring_time": "$agent_transfer_ring_time",
            "billing_circle": {
                "operator": "Reliance Mobile GSM",
                "circle": "Delhi"
            },
            "call_connected": "1",
            "aws_call_recording_identifier": "6433c871d9d5d9c9765448562ae7a410",
            "customer_no_with_prefix ": "918287842425",
            "campaign_name": "$campaign_name",
            "campaign_id": "$campaign_id",
            "customer_ring_time": "4",
            "reason_key": "Call Disconnected By Callee",
            "hangup_cause_description": "Normal call clearing",
            "hangup_cause_code": "16",
            "hangup_cause_key": "NORMAL_CLEARING",
            "ref_id": "02b6990a-84d0-4c05-bb69-23d6ce0af2c6",
            "custom_identifier": "a0hc619uq1"
        }
        """
        call_session_record_id = payload.get("custom_identifier")
        call_hangup_by = "LEAD" if payload.get('reason_key') == "Call Disconnected By Callee" else "AGENT"
        call_hangup_reason = payload.get("hangup_cause_description")
        if not call_session_record_id:
            return {"is_valid": False, "reason": "missing custom_identifier"}

        event_id = payload.get("uuid")
        try:
            call_session_record = frappe.get_doc("Call Session", call_session_record_id)
        except DoesNotExistError:
            return {"is_valid": False, "reason": "Call session record not found"}

        bill_sec = payload.get("billsec")
        call_session_record.set("status", "DISCONNECTED")
        call_session_record.set("hangup_event_log", payload)
        call_session_record.set("hangup_event_id", event_id)
        call_session_record.set("hangup_at", _hangup_at_from_smartflo_payload(payload))
        call_session_record.set("hangup_by", call_hangup_by)
        call_session_record.set("hangup_reason", call_hangup_reason)
        if bill_sec is not None:
            call_session_record.set("duration", flt(bill_sec))
        if not (call_session_record.get("direction") or "").strip():
            call_session_record.set(
                "direction",
                _direction_inbound_outbound_from_vendor_payload(payload),
            )
        call_session_record.save(ignore_permissions=True)

        target_user = call_session_record.get("agent")
        lead_id, lead_name, mobile_no = _call_session_lead_fields(call_session_record)
        phone_display = (call_session_record.get("lead_phone") or mobile_no or "").strip()

        frappe.publish_realtime(
            event="smartflo.call_disconnected",
            message={
                "message": "Call Disconnected",
                "call_session_id": call_session_record.name,
                "lead_id": lead_id,
                "lead_name": lead_name,
                "phone_number": phone_display,
                "to_number": phone_display,
                "timestamp": payload.get("start_stamp"),
                "status": "CALL DISCONNECTED",
                "calling_method": "Click2Call",
                "direction": _call_session_direction_to_ui(
                    call_session_record.get("direction")
                ),
            },
            user=target_user,
        )

        frappe.db.commit()

        return {
            "is_valid": True,
            "reason": None
        }
    
    def submit_disposition_request(self, data: dict):
        """Route disposition by calling_method. Returns {is_valid, reason}."""
        if not isinstance(data, dict):
            data = {}

        call_session_id = str(data.get("call_session_id") or "").strip()
        calling_method = str(data.get("calling_method") or "").strip()
        disposition_status = data.get("disposition_status")
        disposition_code = data.get("disposition_code")
        disposition_remarks = data.get("disposition_remarks")
        sub_disposition = data.get("sub_disposition_status") or data.get(
            "sub_disposition"
        )
        callback_datetime = data.get("callback_datetime")
        callback_comments = data.get("callback_comments")
        remind_before_minutes = data.get("remind_before_minutes")
        expected_call_duration_minutes = data.get("expected_call_duration_minutes")
        scheduled_visit_date = data.get("scheduled_visit_date")
        is_visit_scheduled = data.get("is_visit_scheduled")
        disposition_timing_raw = data.get("disposition_timing") or data.get("disposition_source")
        disposition_timing = (
            str(disposition_timing_raw).strip().upper()
            if disposition_timing_raw
            else "IMMEDIATE"
        )
        if disposition_timing not in ("IMMEDIATE", "LATE"):
            disposition_timing = "IMMEDIATE"

        if not call_session_id or not calling_method:
            return {"is_valid": False, "reason": "missing required fields"}

        ds = str(disposition_status).strip() if disposition_status is not None else ""
        did = str(disposition_code).strip() if disposition_code is not None else ""
        remarks = (
            str(disposition_remarks).strip()
            if disposition_remarks is not None
            else ""
        )
        sub = (
            str(sub_disposition).strip()
            if sub_disposition is not None and str(sub_disposition).strip()
            else None
        )

        if not ds and not did:
            return {
                "is_valid": False,
                "reason": "disposition_status or disposition_code is required",
            }

        match calling_method:
            case "Click2Call":
                return self._handle_click2call_submit_disposition(
                    call_session_id=call_session_id,
                    disposition_status=ds,
                    disposition_code=did,
                    remarks=remarks,
                    sub_disposition=sub,
                    callback_datetime=callback_datetime,
                    callback_comments=callback_comments,
                    remind_before_minutes=remind_before_minutes,
                    expected_call_duration_minutes=expected_call_duration_minutes,
                    disposition_timing=disposition_timing,
                    scheduled_visit_date=scheduled_visit_date,
                    is_visit_scheduled=is_visit_scheduled,
                )
            case "Dialer":
                return self._handle_dialer_submit_disposition(
                    call_session_id=call_session_id,
                    disposition_status=ds,
                    disposition_code=did,
                    remarks=remarks,
                    sub_disposition=sub,
                    disposition_timing=disposition_timing,
                    callback_datetime=callback_datetime,
                    callback_comments=callback_comments,
                    remind_before_minutes=remind_before_minutes,
                    expected_call_duration_minutes=expected_call_duration_minutes,
                    scheduled_visit_date=scheduled_visit_date,
                    is_visit_scheduled=is_visit_scheduled,
                )
            case _:
                return {
                    "is_valid": False,
                    "reason": f"Invalid calling method: {calling_method}",
                }

    def _handle_click2call_submit_disposition(
        self,
        call_session_id: str,
        disposition_status: str,
        disposition_code: str,
        remarks: str,
        sub_disposition: str | None,
        callback_datetime,
        callback_comments,
        remind_before_minutes,
        expected_call_duration_minutes,
        disposition_timing: str,
        scheduled_visit_date=None,
        is_visit_scheduled=None,
    ):
        """Smartflo store-disposition + Call Session update (Click2Call)."""
        try:
            doc = frappe.get_doc("Call Session", call_session_id)
        except DoesNotExistError:
            return {"is_valid": False, "reason": "Call session record not found"}

        unique_id = (doc.get("agent_call_id") or "").strip()
        if not unique_id:
            return {
                "is_valid": False,
                "reason": "Call session has no agent call id; cannot store disposition.",
            }

        if not disposition_code and not disposition_status:
            return {
                "is_valid": False,
                "reason": "disposition_code or disposition_status is required",
            }

        user = frappe.session.user
        # body = {
        #     "disposition_status": str(disposition_status),
        #     "unique_id": unique_id,
        # }
        # if disposition_code is not None:
        #     body["disposition_code"] = str(disposition_code)
        # if sub_disposition is not None:
        #     body["sub_disposition_status"] = sub_disposition

        lead_id = doc.get("lead")

        doc.set("disposition_status", disposition_status or None)
        doc.set("disposition_remarks", remarks or None)
        doc.set("sub_disposition_status", sub_disposition or None)
        doc.set("status", "DISPOSED")
        doc.set("disposed_at", frappe.utils.now())
        doc.set("disposition_timing", disposition_timing or "IMMEDIATE")
        svd = (
            str(scheduled_visit_date).strip()
            if scheduled_visit_date is not None and str(scheduled_visit_date).strip()
            else ""
        )
        want_visit = bool(frappe.utils.cint(is_visit_scheduled)) if is_visit_scheduled is not None else bool(svd)
        if svd and want_visit:
            doc.set("is_visit_scheduled", 1)
            doc.set("scheduled_visit_date", svd)
        else:
            doc.set("is_visit_scheduled", 0)
            doc.set("scheduled_visit_date", None)
        doc.save(ignore_permissions=True)
        if doc.get("scheduled_visit_date") and doc.get("is_visit_scheduled"):
            try:
                util_service.create_event_for_visit_date(
                    lead_id=lead_id,
                    call_session_id=call_session_id,
                    scheduled_visit_date=doc.get("scheduled_visit_date"),
                    disposition_remarks=doc.get("disposition_remarks"),
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "sync_visit_date_event_click2call",
                )
        if lead_id:
            try:
                update_lead_from_call_disposition(
                    lead_id,
                    disposition_status,
                    sub_disposition,
                    remarks,
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "update_lead_from_call_disposition_click2call",
                )
            _set_lead_telecaller(lead_id, doc.get("agent"))
        if callback_datetime:
            util_service.create_event_for_callback(
                lead_id=lead_id,
                call_session_id=call_session_id,
                callback_datetime=callback_datetime,
                callback_comments=callback_comments,
                remind_before_minutes=remind_before_minutes,
                expected_call_duration_minutes=expected_call_duration_minutes)

        frappe.db.commit()

        frappe.publish_realtime(
            event="smartflo.call_disposed",
            message={
                "message": "call disposed",
                "call_id": call_session_id,
                "call_session_id": call_session_id,
                "call_log_name": "",
                "direction": _call_session_direction_to_ui(doc.get("direction")),
            },
            user=user,
        )

        return {"is_valid": True, "reason": None}

    def _handle_dialer_submit_disposition(
        self,
        call_session_id: str,
        disposition_status: str,
        disposition_code: str,
        remarks: str,
        disposition_timing: str,
        sub_disposition: str | None,
        callback_datetime,
        callback_comments,
        remind_before_minutes,
        expected_call_duration_minutes,
        scheduled_visit_date=None,
        is_visit_scheduled=None,
    ):
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_dialer_submit_disposition(
                    call_session_id,
                    disposition_status,
                    disposition_code,
                    remarks,
                    sub_disposition,
                    disposition_timing,
                    callback_datetime,
                    callback_comments,
                    remind_before_minutes,
                    expected_call_duration_minutes,
                    scheduled_visit_date,
                    is_visit_scheduled,
                )
            case _:
                return {
                    "is_valid": False,
                    "reason": f"Invalid telephony vendor: {default_telephony_vendor}",
                }

    def _handle_smartflo_dialer_submit_disposition(
        self,
        call_session_id: str,
        disposition_status: str,
        disposition_code: str,
        remarks: str,
        sub_disposition_status: str | None,
        disposition_timing: str,
        callback_datetime,
        callback_comments,
        remind_before_minutes,
        expected_call_duration_minutes,
        scheduled_visit_date=None,
        is_visit_scheduled=None,
    ):
        try:
            call_session_doc = frappe.get_doc("Call Session", call_session_id)
            if not call_session_doc:
                raise ValueError("Invalid Call Session id: Call session record not found")

            if (call_session_doc.get("calling_method") or "").strip() != "Dialer":
                raise ValueError("Invalid Call Session: expected Dialer calling method")

            call_id = call_session_doc.get("agent_call_id")
            if not call_id:
                raise ValueError("Invalid Call Session id: No agent is connected to this call session")
            lead_id = call_session_doc.get("lead")

            call_session_doc.set("disposition_status", disposition_status)
            call_session_doc.set("sub_disposition_status", sub_disposition_status or None)
            call_session_doc.set("disposition_remarks", remarks)
            call_session_doc.set("disposition_timing", disposition_timing)

            smartflo_client.handle_store_disposition_api(
                user=frappe.session.user,
                call_id=call_id,
                disposition_code=disposition_code,
            )

            svd = (
                str(scheduled_visit_date).strip()
                if scheduled_visit_date is not None and str(scheduled_visit_date).strip()
                else ""
            )
            want_visit = bool(frappe.utils.cint(is_visit_scheduled)) if is_visit_scheduled is not None else bool(svd)
            if svd and want_visit:
                call_session_doc.set("is_visit_scheduled", 1)
                call_session_doc.set("scheduled_visit_date", svd)
            else:
                call_session_doc.set("is_visit_scheduled", 0)
                call_session_doc.set("scheduled_visit_date", None)
            if lead_id:
                try:
                    update_lead_from_call_disposition(
                        lead_id,
                        disposition_status,
                        sub_disposition_status,
                        remarks,
                    )
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        "update_lead_from_call_disposition_dialer",
                    )
                _set_lead_telecaller(lead_id, call_session_doc.get("agent"))

            if callback_datetime:
                util_service.create_event_for_callback(
                    lead_id=lead_id,
                    call_session_id=call_session_id,
                    callback_datetime=callback_datetime,
                    callback_comments=callback_comments,
                    remind_before_minutes=remind_before_minutes,
                    expected_call_duration_minutes=expected_call_duration_minutes
                )

            now = frappe.utils.now()
            call_session_doc.set("disposed_at", now)
            call_session_doc.set("status", "DISPOSED")

            call_session_doc.save(ignore_permissions=True)
            if call_session_doc.get("scheduled_visit_date") and call_session_doc.get("is_visit_scheduled"):
                try:
                    util_service.create_event_for_visit_date(
                        lead_id=lead_id,
                        scheduled_visit_date=call_session_doc.get("scheduled_visit_date"),
                        disposition_remarks=call_session_doc.get("disposition_remarks"),
                        call_session_id=call_session_id,
                    )
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        "sync_visit_date_event_dialer",
                    )
            return {"is_valid": True, "reason": None}
        except Exception as e:
            return {
                "is_valid": False,
                "reason": str(getattr(e, "message", None) or e),
            }

    def _user_has_active_dialer_session(self, user: str) -> bool:
        return bool(
            frappe.db.get_value(
                self.AGENT_DIALER_SESSION_LOG_DOCTYPE,
                {"user": user, "status": "ACTIVE"},
                "name",
            )
        )

    def start_dialer_session(self, user:str, campaign_id: str):
        match default_telephony_vendor:
            case "Smartflo":
                return self._handle_smartflo_start_dialer_session(user,campaign_id)
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

    def _handle_smartflo_start_dialer_session(self, user: str,campaign_id: str):
        try:
            # handle dialer login first
            result = smartflo_client.handle_login_session_api(user,campaign_id)
            if not result.get("is_valid"):
                raise ValueError(result.get("reason"))
        except Exception as e:
            err = str(e)
            if "already logged in" in err.lower():
                pass
            else:
                raise e

        print("============start dialer session=============")
        try:
            # handle dialer session start
            smartflo_client.handle_start_or_end_session_api(user,campaign_id,True)
        except Exception as e:
            print(e)
            return {
                "is_valid": False,
                "reason": str(e)
            }

        
        # update agent dialer session log status to inactive
        frappe.db.sql(
            f"update `tab{self.AGENT_DIALER_SESSION_LOG_DOCTYPE}` set status = %(status)s where user = %(user)s and status = %(active)s",
            {"status": "INACTIVE", "user": user, "active": "ACTIVE"},
        )

        frappe.db.commit()

        # create new agent dialer session log
        doc = frappe.get_doc(
            {
                "doctype": self.AGENT_DIALER_SESSION_LOG_DOCTYPE,
                "user": user,
                "status": "ACTIVE",
                "campaign_id": campaign_id,
                "active_at": frappe.utils.now(),
            }
        )
        doc.insert()
        frappe.db.commit()

        return {
            "is_valid": True,
            "reason": None
        }

    def end_dialer_session(self, user: str):
        data = frappe.db.get_value(
            self.AGENT_DIALER_SESSION_LOG_DOCTYPE,
            {"user": user, "status": "ACTIVE"},
            ["campaign_id", "name"],
            as_dict=True,
        )
        if not data:
            raise ValueError("No active dialer session found")
        match default_telephony_vendor:
            case "Smartflo":
                result = self._handle_smartflo_end_dialer_session(
                    user, campaign_id=data.campaign_id
                )
                if not result.get("is_valid"):
                    raise ValueError(result.get("reason"))
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

        now = frappe.utils.now()
        for br in frappe.get_all(
            self.SESSION_BREAK_LOG_DOCTYPE,
            filters={"user": user, "end_time": ["is", "not set"]},
            pluck="name",
        ):
            frappe.db.set_value(
                self.SESSION_BREAK_LOG_DOCTYPE, br, "end_time", now
            )

        log = frappe.get_doc(self.AGENT_DIALER_SESSION_LOG_DOCTYPE, data.name)
        log.status = "INACTIVE"
        log.inactive_at = now
        log.save()

        frappe.db.commit()

        return {
            "is_valid": True,
            "reason": None,
        }

    def _handle_smartflo_end_dialer_session(self, user: str, campaign_id: str):
        try:
            smartflo_client.handle_start_or_end_session_api(user,campaign_id,False)
        except Exception as e:
            return {
                "is_valid": False,
                "reason": str(getattr(e, "message", None) or e)
            }

        return {
            "is_valid": True,
            "reason": None
        }

    def start_dialer_break(self, user: str, break_code: str):
        code = (break_code or "").strip()
        if not code:
            raise ValueError("break_code is required")

        match default_telephony_vendor:
            case "Smartflo":
                result = self._handle_smartflo_start_dialer_break(user, code)
                if not result.get("is_valid"):
                    raise ValueError(result.get("reason"))
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

        data = frappe.db.get_value(
            self.AGENT_DIALER_SESSION_LOG_DOCTYPE,
            {"user": user, "status": "ACTIVE"},
            ["campaign_id", "name"],
            as_dict=True,
        )
        if not data:
            raise ValueError("No active dialer session found")

        doc = frappe.new_doc(self.SESSION_BREAK_LOG_DOCTYPE)
        doc.set("user", user)
        doc.set("break_code", code)
        doc.set("start_time", frappe.utils.now())
        doc.set("user_dialer_session_log", data.name)
        doc.insert()
        frappe.db.commit()

        return {
            "is_valid": True,
            "reason": None,
        }

    def _handle_smartflo_start_dialer_break(self, user: str, break_code: str):
        try:
            smartflo_client.handle_start_dialer_break(user, break_code)
        except Exception as e:
            return {
                "is_valid": False,
                "reason": str(getattr(e, "message", None) or e),
            }
        return {"is_valid": True, "reason": None}

    def end_dialer_break(self, user: str):
        match default_telephony_vendor:
            case "Smartflo":
                result = self._handle_smartflo_end_dialer_break(user)
                if not result.get("is_valid"):
                    raise ValueError(result.get("reason"))
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

        open_break = frappe.get_all(
            self.SESSION_BREAK_LOG_DOCTYPE,
            filters={"user": user, "end_time": ["is", "not set"]},
            fields=["name"],
            order_by="start_time desc",
            limit_page_length=1,
        )
        if open_break:
            doc = frappe.get_doc(self.SESSION_BREAK_LOG_DOCTYPE, open_break[0].name)
            doc.end_time = frappe.utils.now()
            doc.save()

        frappe.db.commit()

        return {
            "is_valid": True,
            "reason": None,
        }

    def _handle_smartflo_end_dialer_break(self, user: str):
        try:
            smartflo_client.handle_end_dialer_break(user)
        except Exception as e:
            return {
                "is_valid": False,
                "reason": str(getattr(e, "message", None) or e),
            }

        return {
            "is_valid": True,
            "reason": None,
        }

    def get_dialer_break_status(self, user: str):
        active_session = frappe.db.get_value(
            self.AGENT_DIALER_SESSION_LOG_DOCTYPE,
            {"user": user, "status": "ACTIVE"},
            ["campaign_id", "name"],
            as_dict=True,
        )
        open_break = frappe.get_all(
            self.SESSION_BREAK_LOG_DOCTYPE,
            filters={"user": user, "end_time": ["is", "not set"]},
            fields=["name"],
            limit_page_length=1,
        )
        cred = get_smartflo_credentials_for_frappe_user(user) or {}
        default_campaign_id = cred.get("defaultCampaignId") or cred.get(
            "default_campaign_id"
        )
        campaign_id = active_session.campaign_id if active_session else None
        return {
            "is_valid": True,
            "on_break": bool(open_break),
            "is_active_session": bool(active_session),
            "campaign_id": campaign_id,
            "campaignId": campaign_id,
            "status": "ACTIVE" if active_session else "INACTIVE",
            "defaultCampaignId": default_campaign_id,
            "default_campaign_id": default_campaign_id,
        }

    def _get_user_for_agent_email(self,agent_email):
        """
        Map Smartflo agent email (external id) to Frappe user via Carrum credentialType=smartflow lookup.
        """
        if not agent_email:
            return None

        agent_detail = get_frappe_user_by_smartflo_account(agent_email)
        if not agent_detail:
            return None
        return agent_detail.get("frappe_user")

    def _parse_call_timestamp(self,start_date: str, start_time: str):
        """Parse start_date and start_time; supports '2/24/2026' and '2:19:58' or ISO-style."""
        if not start_date or not start_time:
            return None
        try:
            # Smartflo format: "2/24/2026", "2:19:58"
            if isinstance(start_date, str) and "/" in start_date and isinstance(start_time, str):
                date_obj = datetime.strptime(start_date.strip(), "%m/%d/%Y").date()
                time_obj = datetime.strptime(start_time.strip(), "%H:%M:%S").time()
                return datetime.combine(date_obj, time_obj)
        except (ValueError, TypeError):
            pass
        try:
            date_obj = getdate(start_date) if isinstance(start_date, str) else start_date
            time_obj = get_time(start_time) if isinstance(start_time, str) else start_time
            return datetime.combine(date_obj, time_obj)
        except (ValueError, TypeError):
            return None


    def _find_crm_lead_doc_for_phone(self, phone_raw: str):
        """Return saved CRM Lead doc if ``mobile_no`` matches (tries common stored formats)."""
        if not phone_raw or not str(phone_raw).strip():
            return None
        raw = str(phone_raw).strip()
        digits = re.sub(r"\D", "", raw)
        parsed = parse_phone_number(raw)
        national = parsed.get("national_number") if parsed.get("success") else None

        variants = []
        for v in (raw, national, digits):
            if v:
                variants.append(str(v).strip())
        if national:
            variants.append(f"+91{national}")
            if len(national) >= 10:
                variants.append(national[-10:])
        if len(digits) >= 10:
            variants.append(digits[-10:])
            variants.append(f"+{digits}")

        seen = set()
        for v in variants:
            if not v or v in seen:
                continue
            seen.add(v)
            lead_name = frappe.db.get_value("CRM Lead", {"mobile_no": v}, "name")
            if lead_name:
                return frappe.get_doc("CRM Lead", lead_name)
        return None

    def _create_lead_if_not_exists(self, phone_number: str):
        """Return a saved CRM Lead for the given phone: existing if found, else create."""
        lead = self._find_crm_lead_doc_for_phone(phone_number)
        if lead:
            return lead

        raw = str(phone_number or "").strip()
        if not raw:
            return None

        parsed = parse_phone_number(raw)
        mobile_to_store = parsed.get("national_number") if parsed.get("success") else None
        if not mobile_to_store:
            digits = re.sub(r"\D", "", raw)
            mobile_to_store = digits[-10:] if len(digits) >= 10 else digits
        if not mobile_to_store:
            return None

        status_list = frappe.get_all(
            "CRM Lead Status",
            pluck="name",
            order_by="position asc, creation asc",
            limit=1,
        )
        default_status = status_list[0] if status_list else None
        lead = frappe.new_doc("CRM Lead")
        lead.mobile_no = mobile_to_store
        if default_status:
            lead.status = default_status
        lead.flags.ignore_mandatory = True
        lead.insert(ignore_permissions=True)
        return lead

    def dialer_call_connected(self, user: str, payload: dict):
        call_id = payload.get("call_id")
        event_id = payload.get("uuid")
        to_number = payload.get("call_to_number")
        caller_id_number = payload.get("caller_id_number")
        start_date = payload.get("start_date")
        start_time = payload.get("start_time")
        agent_list = payload.get("agent") or []
        if isinstance(agent_list, dict):
            agent_email = agent_list.get("email")
        else:
            agent_email = agent_list[0].get("email") if agent_list else None

        target_user = self._get_user_for_agent_email(agent_email)
        timestamp = self._parse_call_timestamp(start_date, start_time)

        lead = self._create_lead_if_not_exists(to_number)
        if not lead or not getattr(lead, "name", None):
            frappe.throw(
                frappe._("Could not resolve or create CRM Lead for customer number {0}").format(
                    to_number or ""
                )
            )
        
        DID_SOURCE_MAPPING = frappe.get_doc("Global Config", {
            "key": "DID_SOURCE_MAPPING"
        })
        did_source_map = {}
        if DID_SOURCE_MAPPING:
            did_source_map = json.loads(DID_SOURCE_MAPPING.value)

        newSource = did_source_map.get(caller_id_number) or did_source_map.get(to_number)
        if newSource is not None:
            lead.set('current_source',newSource)
            lead.save(ignore_permissions=True)
        
        direction = payload.get("direction")
        if direction == "Dialer (outbound)":
            direction = "OUTBOUND"
        else:
            direction = "INBOUND"

        
        new_call_session_doc = frappe.new_doc(
            "Call Session",
            calling_method="Dialer",
            direction=direction,
            agent=target_user,
            vendor_agent_id=agent_email,
            lead=lead.name,
            lead_phone=to_number,
            agent_call_id=call_id,
            status="CUSTOMER_CONNECTED",
            agent_answered_at=timestamp,
            agent_answer_event_id=event_id,
            agent_answer_event_log=payload,
            vendor_name=default_telephony_vendor,
        )

        new_call_session_doc.insert(ignore_permissions=True)
        if direction == "OUTBOUND":
            enqueue_complete_today_callback_followups_for_lead(lead.name)
        frappe.db.commit()

        if target_user is not None:
            lead_id = lead.name
            lead_name = lead.lead_name
            phone_display = (lead.get("mobile_no") or "").strip() 
            start_stamp = timestamp
            frappe.publish_realtime(
                event="call_customer_connected",
                message={
                    "call_session_id": new_call_session_doc.name,
                    "lead_id": lead_id,
                    "lead_name": lead_name,
                    "phone_number": phone_display,
                    "to_number": phone_display,
                    "timestamp": start_stamp,
                    "status": "CUSTOMER CONNECTED",
                    "calling_method": "Dialer",
                    "direction": _call_session_direction_to_ui(
                        new_call_session_doc.get("direction") or direction
                    ),
                },
                user=target_user,
                after_commit=True
            )
            frappe.db.commit()
        return {"message": "outbound connected"}

    def dialer_call_disposed_webhook(self, user: str, payload: dict):
        result = {}
        match default_telephony_vendor:
            case "Smartflo":
                result = self._handle_smartflo_dialer_call_disposed_webhook(payload)
                if not result.get("is_valid"):
                    raise ValueError(result.get("reason"))
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")
        return {
            "message": (
                "call disposed (duplicate or in-flight event skipped)"
                if result.get("skipped")
                else "call disposed"
            ),
        }

    def _handle_smartflo_dialer_call_disposed_webhook(self, payload: dict):
        """
        Smartflo dialer call disposed webhook. Idempotent on payload uuid (event_id).
        Enriches vendor payload when the agent already submitted disposition (DISPOSED) first.
        """
        call_id = payload.get("call_id")
        if not call_id:
            return {"is_valid": False, "reason": "missing call_id"}

        event_id = (payload.get("uuid") or "").strip() or None

        row_name = frappe.db.get_value("Call Session", {"agent_call_id": call_id})
        if not row_name:
            return {"is_valid": False, "reason": "call session not found"}

        row = frappe.get_doc("Call Session", row_name)
        if event_id and (row.get("disposition_event_id") or "").strip() == event_id:
            return {"is_valid": True, "skipped": True}

        if event_id:
            if not _webhook_acquire_lock(f"dialer_disposed:{event_id}", ttl=120):
                return {"is_valid": True, "skipped": True}
            row.reload()
            if (row.get("disposition_event_id") or "").strip() == event_id:
                return {"is_valid": True, "skipped": True}

        row.set("disposition_event_id", event_id)
        row.set("disposition_raw", payload)
        if not row.get("disposed_at"):
            row.set("disposed_at", frappe.utils.now())
        row.set("status", "DISPOSED")
        row.save(ignore_permissions=True)
        frappe.db.commit()
        return {"is_valid": True}
    def dialer_call_disconnected(self, user: str, payload: dict):
        match default_telephony_vendor:
            case "Smartflo":
                result = self._handle_smartflo_dialer_call_disconnected(payload)
                if not result.get("is_valid"):
                    raise ValueError(result.get("reason"))
                return {"message": "call disconnected"}
            case _:
                raise ValueError(f"Invalid telephony vendor: {default_telephony_vendor}")

    def _handle_smartflo_dialer_call_disconnected(self, payload: dict):
        """
        Handle Smartflo Dialer Call Disconnected Event
        """

        frappe.logger().info(f"Dialer Disconnected Payload: {payload}")

        call_id = payload.get("call_id")
        if not call_id:
            return {"is_valid": False, "reason": "missing call_id"}

        event_id = payload.get("uuid")

        row_name = frappe.db.get_value("Call Session", {"agent_call_id": call_id})
        lead = self._create_lead_if_not_exists(payload.get("call_to_number"))
        if not lead or not getattr(lead, "name", None):
            frappe.throw(
                frappe._("Could not resolve or create CRM Lead for customer number {0}").format(
                    payload.get("call_to_number") or ""
                )
            )

        call_direction = "OUTBOUND" if payload.get("direction") == "Dialer (outbound)" else "INBOUND"
        if not row_name:
            call_status = frappe.new_doc("Call Session")
            call_status.agent_call_id = call_id
            call_status.vendor_name = "Smartflo"
            call_status.calling_method = "Dialer"
            call_status.lead = lead.name
            call_status.lead_phone = lead.get("mobile_no") or ""
            call_status.direction = call_direction
            call_status.status = "NOT_CONNECTED" if call_direction == "OUTBOUND" else "MISSED"
            call_status.insert(ignore_permissions=True)
            row_name = call_status.name

        row = frappe.get_doc("Call Session", row_name)
        pre_status = (row.get("status") or "").strip().upper()
        is_outbound = (row.get("direction") or "").strip().upper() == "OUTBOUND"
        had_agent_connection = pre_status in ("AGENT_CONNECTED", "CUSTOMER_CONNECTED")
        lead_for_followup = (row.get("lead") or "").strip()
        row.hangup_event_id = event_id
        row.hangup_event_log = payload
        row.hangup_at = frappe.utils.now()
        if pre_status in ("DISPOSED", "DISCONNECTED"):
            pass
        elif had_agent_connection:
            row.set("status", "DISCONNECTED")
        else:
            row.set("status", "NOT_CONNECTED" if is_outbound else "MISSED")
        row.save(ignore_permissions=True)
        if (
            is_outbound
            and not had_agent_connection
            and lead_for_followup
            and pre_status not in ("DISPOSED", "DISCONNECTED")
        ):
            _enqueue_apply_not_connected_dial_for_today_lead_callback(
                lead_for_followup,
                lock_key=(
                    str(event_id or "").strip()
                    or str(call_id or "").strip()
                    or None
                ),
            )
        frappe.db.commit()

        target_user = row.agent
        lead_id = row.lead
        # lead_name = row.lead_name
        phone_display = (row.lead_phone or "").strip()
        start_stamp = row.lead_answered_at

        agent_call_id = (row.get("agent_call_id") or "").strip()
        frappe.publish_realtime(
            event="call_disconnected",
            message={
                "call_session_id": row.name,
                "call_id": agent_call_id,
                "lead_id": lead_id,
                "phone_number": phone_display,
                "to_number": phone_display,
                "timestamp": start_stamp,
                "status": "CALL DISCONNECTED",
                "calling_method": "Dialer",
                "message": "Call Disconnected",
                "direction": _call_session_direction_to_ui(row.get("direction")),
            },
            user=target_user,
        )

        return {"is_valid": True}

    def get_last_call(self, user: str):
        """Latest Call Session for this agent; shape matches LastCallStatusModal / CustomCallUI."""
        if not user or user == "Guest":
            return None
        rows = frappe.get_all(
            "Call Session",
            filters={"agent": user},
            order_by="modified desc",
            limit_page_length=1,
            fields=[
                "name",
                "calling_method",
                "lead",
                "lead_phone",
                "agent_call_id",
                "direction",
                "status",
                "lead_answered_at",
                "agent_answered_at",
                "duration",
                "disposition_status",
                "disposition_remarks",
                "disposed_at",
            ],
        )
        if not rows:
            return None
        row = rows[0]
        status = row.get("status") or ""
        status_upper = status.strip().upper()
        is_disposed = status_upper == "DISPOSED"
        ui_status = _call_session_status_to_ui_bucket(status)
        lead_id = row.get("lead")
        lead_name = frappe.db.get_value("CRM Lead", lead_id, "lead_name") if lead_id else None

        call_id = row.get("agent_call_id")
        if call_id is not None:
            call_id = str(call_id).strip() or None

        start_time = row.get("lead_answered_at") or row.get("agent_answered_at")
        lead_phone = (row.get("lead_phone") or "").strip()
        disp_remarks = row.get("disposition_remarks") or ""

        return {
            "call_session_id": row.get("name"),
            "call_log_name": "",
            "call_id": call_id,
            "lead_id": lead_id,
            "lead_name": lead_name,
            "reference_doctype": "CRM Lead" if lead_id else None,
            "reference_docname": lead_id,
            "from_number": "",
            "to_number": lead_phone,
            "phone_number": lead_phone,
            "duration_seconds": _duration_seconds_from_value(row.get("duration")),
            "direction": _call_session_direction_to_ui(row.get("direction")),
            "status": status,
            "ui_status": ui_status,
            "disposition": row.get("disposition_status") or "",
            "disposition_remarks": disp_remarks if is_disposed else "",
            "is_disposed": is_disposed,
            "start_time": start_time,
            "calling_method": (row.get("calling_method") or "Dialer").strip(),
        }




_service = CallService()


def start_call(calling_method: str, leadId: str, user: str, manual_dial: bool = False):
    return _service.start_call(
        calling_method, leadId, user, manual_dial=bool(manual_dial)
    )


def end_call(calling_method: str, call_id: str, user: str):
    return _service.end_call(calling_method, call_id, user)


def submit_disposition_request(data: dict):
    """Whitelisted entry: pass JSON body as dict."""
    return _service.submit_disposition_request(data)


def reconcile_active_calls():
    return _service.reconcile_active_calls()

def initiate_stale_call_as_failed(call_session_id: str):
    return _service._mark_initiated_stale_calls_as_failed(call_session_id)

def handle_agent_call_connected_webhook(vendor_name: str, payload: dict):
    return _service.handle_agent_call_connected_webhook(vendor_name, payload)


def handle_customer_call_connected_webhook(vendor_name: str, payload: dict):
    return _service.handle_customer_call_connected_webhook(vendor_name, payload)


def handle_call_missed_by_customer_webhook(vendor_name: str, payload: dict):
    return _service.handle_call_missed_by_customer_webhook(vendor_name, payload)


def handle_answered_call_hangup_webhook(vendor_name: str, payload: dict):
    return _service.handle_answered_call_hangup_webhook(vendor_name, payload)


def update_lead_last_call_date_time(doc, method):
    """When Call Session.hangup_at is set, roll CRM Lead last_call_* forward if this hangup is newer."""
    lead_id = (doc.get("lead") or "").strip()
    if not lead_id:
        return

    hangup_raw = doc.get("hangup_at")
    if not hangup_raw:
        return

    hangup_dt = get_datetime(hangup_raw)
    if not hangup_dt:
        return

    saved = _lead_last_call_datetime_from_db(lead_id)
    if saved and hangup_dt <= saved:
        return

    frappe.db.set_value(
        "CRM Lead",
        lead_id,
        {
            "last_call_date": hangup_dt.date(),
            "last_call_time": hangup_dt.time(),
        },
        update_modified=False,
    )

def start_dialer_session(user,payload: dict):
    campaign_id = payload.get("campaign_id")
    if not campaign_id:
        raise ValueError("campaign_id is required")
    return _service.start_dialer_session(user,campaign_id)

def end_dialer_session(user: str):
    return _service.end_dialer_session(user)


def toggle_dialer_break(user: str, payload: dict):
    break_type = (payload.get("break_type") or "").strip()
    break_code = payload.get("break_code")
    if break_type == "start":
        return _service.start_dialer_break(user, break_code)
    if break_type == "end":
        return _service.end_dialer_break(user)
    raise ValueError("Invalid break_type; expected 'start' or 'end'")

def get_dialer_break_status(user: str):
    return _service.get_dialer_break_status(user)

def dialer_call_connected(user: str, payload: dict):
    return _service.dialer_call_connected(user, payload)

def dialer_call_disconnected(user: str, payload: dict):
    return _service.dialer_call_disconnected(user, payload)

def dialer_call_disposed(user: str, payload: dict):
    return _service.dialer_call_disposed_webhook(user, payload)

def get_last_call(user: str):
    return _service.get_last_call(user)

def create_callback_event(
    lead_id,
    call_session_id,
    callback_datetime,
    callback_comments,
    remind_before_minutes,
    expected_call_duration_minutes,
):
    return util_service.create_event_for_callback(lead_id, call_session_id, callback_datetime, callback_comments, remind_before_minutes, expected_call_duration_minutes)