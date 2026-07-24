import time

import frappe
import requests
from core.services.apihit_service import (
	api_hit_service,
	created_by_user,
	request_headers_for_log,
	response_body_for_log,
)

CALLMATIC_WEBHOOK_PATH = "/api/method/core.api.call.callmatic_start_call_webhook"


def get_callmatic_callback_url() -> str:
    # return frappe.utils.get_url(CALLMATIC_WEBHOOK_PATH)
    hostname = frappe.conf.get("hostname")

    print(hostname)
    return f"{hostname}{CALLMATIC_WEBHOOK_PATH}"


class CallmaticClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.callmatic_base_url = "https://api.callmatic.ai/v1"
        self.webhook_url = get_callmatic_callback_url()

    def trigger_call(
        self,
        from_number: str,
        to_number: str,
        campaign_id: str,
        did_number: str,
        call_session_id: str,
        user: str | None = None,
        campaign_name: str | None = None
    ):
        url = f"{self.callmatic_base_url}/calls"

        if not self.api_key:
            return {
                "is_valid": False,
                "message": "API Key is not found in configuration, connect with Engineering team @kapil.rohilla@carrum.co.in",
            }
        headers = {
            "api-key": f"{self.api_key}"
        }
  
        data = {
            "campaignId": campaign_id,
            "phoneNumber": from_number,  
            "variables": {
                "fromNumber": did_number,  
                "transferNumber": to_number, 
                "callSessionId": call_session_id  
            }
        }

        created_by = created_by_user(user)
        t0 = time.perf_counter()
        response = None
        response_data = None

        try:
            response = requests.post(url=url, json=data, headers=headers)
            response_data = response_body_for_log(response)
            api_hit_service.log_api_request(
                "Callmatic:trigger_call",
                url,
                data,
                response_data,
                response.status_code,
                time.perf_counter() - t0,
                headers=request_headers_for_log(response),
                created_by=created_by,
            )

            if response.status_code == 401:
                return {
                    "is_valid": False,
                    "message": "Invalid API Key, connect with Engineering team @kapil.rohilla@carrum.co.in",
                }
        except Exception as e:
            api_hit_service.log_api_request(
                "Callmatic:trigger_call",
                url,
                data,
                response_body_for_log(response),
                int(response.status_code) if response is not None else 0,
                time.perf_counter() - t0,
                headers=request_headers_for_log(response),
                error_message=str(e),
                created_by=created_by,
            )
            return {
                "is_valid": False,
                "message": str(e)
            }

        return {
            "is_valid": True,
            'url': url,
            'response_data': response_data,
        }


callmatic_client = CallmaticClient(api_key=frappe.conf.get("callmatic_api_key"))
