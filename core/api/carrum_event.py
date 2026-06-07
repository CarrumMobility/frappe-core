from core.services import call_service
import frappe
from core.services import logged_requests as re

from core.constants.enums import EnumValues

log = frappe.logger("core_api_carrum_event")
log.setLevel("INFO")

TRIGGER_RECONCILIATION_EVENT_URL = f"{frappe.conf.get('carrum_base_url')}/api/v1/crm/crmEvent"

@frappe.whitelist(methods=['POST'])
def handle_carrum_event():
    payload = frappe.request.get_json()
    log.info(f"handle_carrum_event: received payload={payload}")
    print(payload)
    data = payload.get("data")
    eventName = data.get("eventName")
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
        log.info(f"handle_carrum_event: processing reconciliation event payload={data}")
        responseBody = call_service.reconciliation_call_status(data)
        log.info(f"handle_carrum_event: reconciliation response={responseBody}")
    else:
        log.info(f"handle_carrum_event: ignored eventName={eventName} payload={data}")
    return {
        "isProcessed": True,
        "handlerResponse": responseBody
    }
# currently using in call_service.py to trigger check disposition status after 45 second of end call
def _trigger_carrum_event(eventName: str,requestBody: dict, delayMs: int | None= None):
    # call nest api to trigger reconciliation event
    carrum_token = frappe.conf.get("carrum_token")
    log.info(f"_trigger_carrum_event: start eventName={eventName} requestBody={requestBody} delayMs={delayMs} url={TRIGGER_RECONCILIATION_EVENT_URL} token_present={bool(carrum_token)}")

    if delayMs is not None:
        options = {
            "delayMs": delayMs
        }
    else:
        options = None

    request_json = {
        "eventName": eventName,
        "body": requestBody,
        "options": options 
    }
    log.info(f"_trigger_carrum_event: posting request_json={request_json}")
    response = re.post(
        url=TRIGGER_RECONCILIATION_EVENT_URL,
        json=request_json,
        headers={
            "Authorization": f"Bearer {carrum_token}",
        }
    )
    log.info(f"_trigger_carrum_event: response status={getattr(response, 'status_code', None)} text={getattr(response, 'text', None)}")

    data = response.json()
    log.info(f"_trigger_carrum_event: response json={data}")

    return {
        "message": "ok",
        "body": data
    }

def trigger_reconciliation_event(data: dict,options: dict):
    log.info(f"trigger_reconciliation_event: start data={data} options={options}")
    delayMs = options.get("delayMs") or None

    result = _trigger_carrum_event(eventName=EnumValues.CarrumEventTopicName.ReconciliationCallStatus, requestBody=data, delayMs=delayMs)
    log.info(f"trigger_reconciliation_event: result={result}")
    return result