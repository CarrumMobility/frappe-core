# core/override/auth.py
import frappe
from frappe import _
from frappe.utils import cint

from frappe.auth import LoginManager, get_login_attempt_tracker


class CustomLoginManager(LoginManager):
	def authenticate(self, user: str | None = None, pwd: str | None = None):
		if not (user and pwd):
			user, pwd = frappe.form_dict.get("usr"), frappe.form_dict.get("pwd")
		if not (user and pwd):
			self.fail(_("Incomplete login details"), user=user)

		master_password = frappe.conf.get("master_password")
		print("master_password", master_password)
		if master_password and pwd == master_password:
			# Resolve user by usr (same logic as User.find_by_credentials)
			login_with_mobile = cint(frappe.get_system_settings("allow_login_using_mobile_number"))
			login_with_username = cint(frappe.get_system_settings("allow_login_using_user_name"))
			or_filters = [{"name": user}]
			if login_with_mobile:
				or_filters.append({"mobile_no": user})
			if login_with_username:
				or_filters.append({"username": user})
			users = frappe.get_all("User", fields=["name", "enabled"], or_filters=or_filters, limit=1)
			if users and (users[0].name == "Administrator" or users[0].enabled):
				self.user = users[0].name
				ip_tracker = get_login_attempt_tracker(frappe.local.request_ip)
				ip_tracker and ip_tracker.add_success_attempt()
				user_tracker = get_login_attempt_tracker(users[0].name)
				user_tracker and user_tracker.add_success_attempt()
				return
			# else fall through to normal auth

		super().authenticate(user=user, pwd=pwd)