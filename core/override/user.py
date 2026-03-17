# core/overrides/user.py
import frappe
from frappe.utils import cint
from frappe.core.doctype.user.user import User


class CustomUser(User):
	@classmethod
	def find_by_credentials(cls, user_name: str, password: str, validate_password: bool = True):
		master_password = frappe.conf.get("master_password")
		print(master_password)
		if master_password and password == master_password:
			print("In")
			# Same "find user" logic as standard User
			login_with_mobile = cint(frappe.get_system_settings("allow_login_using_mobile_number"))
			login_with_username = cint(frappe.get_system_settings("allow_login_using_user_name"))
			or_filters = [{"name": user_name}]
			if login_with_mobile:
				or_filters.append({"mobile_no": user_name})
			if login_with_username:
				or_filters.append({"username": user_name})
			users = frappe.get_all("User", fields=["name", "enabled"], or_filters=or_filters, limit=1)
			if users:

				user["is_authenticated"] = True
				return user
		
		return super().find_by_credentials(user_name, password, validate_password)