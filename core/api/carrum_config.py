import json
import frappe
import requests

carrumBaseUrl = frappe.conf.get("carrum_base_url") + "/api/v1/config/key";

carrumToken= frappe.conf.get("carrum_token")
logger = frappe.logger("core::carrum_config")

@frappe.whitelist()
def getConfigByKey(key: str = None) -> str:
    data = frappe.request.get_json() or {}
    key = key or data.get("key") or (data.get("args") or [None])[0]
    if not key:
        frappe.throw("Key is required")

    headers = {
        "Authorization": carrumToken
    }

    url = carrumBaseUrl + "/" + key
    print(url)
    print(headers)
    res = requests.get(url, headers=headers)

    value = res.json()
    logger.info("getCarrumConfigByKey: %s", json.dumps(value, indent=4))

    return value


# def updatePaymentAmountForCapture(amount: float, phoneNumber: str) -> str:
#     leadId = frappe.db.get_value("CRM Lead", filters={"phone_number": phoneNumber}, fieldname="name")
#     if not leadId:
#         lead = frappe.get_doc({
#             "doctype": "CRM Lead",
#             "phone_number": phoneNumber,
#             "lead_type": "DRIVER",
#             "total_paid_amount": amount
#         })
#         lead.insert(ignore_permissions=True)
#         frappe.db.commit()
#         return "success"

#     lead = frappe.get_doc("CRM Lead", leadId)

#     if lead.lead_type == 'LEAD':
#         lead.lead_type = "DRIVER"
        
#     lead.total_paid_amount = amount + lead.total_paid_amount
#     lead.save(ignore_permissions=True)
#     frappe.db.commit()
#     return "success"

# def updatePaymentAmountForFailed(amount, phoneNumber: str) -> str:
#     pass   

# @frappe.whitelist()
# def updatePaymentAmount(amount: float, status: str, phoneNumber: str) -> str:
#     if status != "CAPTURED" or status != "FAILED": 
#         frappe.throw("Invalid status")

#     match status:
#         case "CAPTURED":
#             updatePaymentAmountForCapture(amount, phoneNumber)
#         case "FAILED":
#             updatePaymentAmountForFailed(amount, phoneNumber)
