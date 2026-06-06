import frappe


@frappe.whitelist(methods=['POST'])
def handle_carrum_event():
    payload = frappe.request.get_json()

    return {
        "message": "ok",
        "body": payload
    }