import frappe
import requests as re
from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username

carrum_base_url = frappe.conf.get("old_carrum_base_url")
carrum_token = frappe.conf.get("old_carrum_token")

@frappe.whitelist()
def get_business_type_list():
    # usr = frappe.session.user
    # userData = fetch_carrum_user_data_using_frappe_username(usr)

    # if not userData:
    #     return {
    #         "success": False,
    #         "message": "Carrum user data not found"
    #     }

    # hubId = userData.get("defaultHub").get("id")
    # if not hubId:
    #     return {
    #         "success": False,
    #         "message": "Carrum hub id not found"
    #     }

    # hubId = "779db382-859d-48ee-ba17-d90ffa91cf24"

    # url = f"{carrum_base_url}/api/v1/hubs/hub_details/{hubId}"
    # print(url)
    # response = re.get(url, headers={"Authorization": carrum_token})
    # print(response)
    # if not response.ok:
    #     return {
    #         "success": False,
    #         "message": "Failed to get hub details"
    #     }

    # data = response.json()

    # responseData = data.get("results")
    responseData = {
        "status": "success",
        "message": "Ok",
        "results": [
            {"type": "black", "hubId": "4eca097a-9b88-4934-a796-fcf0594c67e8"},
            {"type": "go", "hubId": "779db382-859d-48ee-ba17-d90ffa91cf24"}
        ]
    }


    return {
        "success": True,
        "data": responseData.get('results')
    }