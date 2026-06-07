from core.services import call_service
import frappe
from core.services.logged_requests import request as re

from core.constants.enums import EnumValues


TRIGGER_RECONCILIATION_EVENT_URL = f"{frappe.conf.get('carrum_base_url')}/api/v1/event/trigger-reconciliation-event"

@frappe.whitelist(methods=['POST'])
def handle_carrum_event():
    payload = frappe.request.get_json()
    print(payload)
    eventName = payload.get("eventName")
    responseBody = None

    if eventName == EnumValues.CarrumEventTopicName.ReconciliationCallStatus:
        '''
        payload should be like this:
        {
            "call_session_id": "CL00000000001",
            "vendor_name": "Smartflo",
            "calling_method": "Dialer"
        }
        '''
        responseBody = call_service.reconciliation_call_status(payload)
    return {
        "isProcessed": True,
        "handlerResponse": responseBody
    }
# currently using in call_service.py to trigger check disposition status after 45 second of end call
def _trigger_carrum_event(eventName: str,requestBody: dict, delayMs: int | None= None):
    # call nest api to trigger reconciliation event
    carrum_token = frappe.conf.get("carrum_token")

    if delayMs is not None:
        options = {
            "delayMs": delayMs
        }
    else:
        options = None

    response = re.post(
        url=TRIGGER_RECONCILIATION_EVENT_URL,
        json={
            "eventName": eventName,
            "body": requestBody,
            "options": options 
        },
        headers={
            "Authorization": f"Bearer {carrum_token}",
        }
    )

    data = response.json()

    return {
        "message": "ok",
        "body": data
    }

def trigger_reconciliation_event(data: dict,options: dict):
    delayMs = options.get("delayMs") or None

    return _trigger_carrum_event(eventName=EnumValues.CarrumEventTopicName.ReconciliationCallStatus, requestBody=data, delayMs=delayMs)