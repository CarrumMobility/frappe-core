import frappe


def getCarrumBaseUrl():
    return frappe.conf.get("carrum_base_url")


carrumAccountByApiUrl = lambda frappeUser: getCarrumBaseUrl() + "/api/v2/accounts/by-frappe-user?frappe_user=" + frappeUser
