import frappe
import requests

CALLMATIC_WEBHOOK_PATH = "/api/method/core.api.call.callmatic_start_call_webhook"


def get_callmatic_callback_url() -> str:
    return frappe.utils.get_url(CALLMATIC_WEBHOOK_PATH)

class CallmaticClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.callmatic_base_url = "https://api.callmatic.ai/v1"
        self.webhook_url = get_callmatic_callback_url()

    def trigger_call(self,from_number: str, to_number: str, campaign_id: str, did_number: str, call_session_id: str):
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
            "phoneNumber": from_number,
            "campaignId": campaign_id,
            "variables": {
                "transferNumber": to_number,
                "callback": self.webhook_url,
                "fromNumber": f"{did_number}",
                "callSessionId": call_session_id
            }
        }

        response_data = None
        try:
            response = requests.post(url=url,json=data,headers=headers)

            response_data = response.json()
            if response.status_code == 401:
                return {
                    "is_valid": False,
                    "message": "Invalid API Key, connect with Engineering team @kapil.rohilla@carrum.co.in",
                }
        except Exception as e:
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