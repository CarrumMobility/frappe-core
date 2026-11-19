import secrets

import frappe
from frappe import _
from frappe.utils.password import update_password

PROTECTED_USERS = frozenset({"Administrator", "Guest"})
PASSWORD_BYTES = 24


@frappe.whitelist(methods=["POST"])
def generate_user_password(user: str) -> dict:
	"""Set a new random password on ``user`` and return it once.

	Only the hash is stored, so the plaintext cannot be read back later; calling this
	again rotates the password. Existing sessions of the user stay logged in.
	"""
	frappe.only_for("System Manager")

	user = (user or "").strip()
	name = frappe.db.exists("User", user) or frappe.db.exists("User", user.lower())
	if not name:
		frappe.throw(_("User {0} not found").format(user), frappe.DoesNotExistError)
	if name in PROTECTED_USERS:
		frappe.throw(_("Password of {0} cannot be generated").format(name), frappe.PermissionError)

	password = secrets.token_urlsafe(PASSWORD_BYTES)
	update_password(name, password)
	frappe.logger("core::user").info(
		"Password generated for user %s by %s", name, frappe.session.user
	)
	return {"user": name, "password": password}
