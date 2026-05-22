# Copyright (c) 2025, Core and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Allow guest access so SSO page can load and perform cookie-based login."""
	context.no_cache = 1
	# redirect-to is required (from query params); no default
	context.redirect_to = frappe.form_dict.get("redirect-to") or None
	# site_config.json key "env" (e.g. DEV, QA, PROD) — exposed only as env name, not secrets
	context.env = (frappe.conf.get("env") or "").strip()
	# External SSO targets from site_config.json; UI falls back to /login and /dashboard.
	# Used by sso.html to redirect unauthenticated users straight to the external login
	# screen instead of bouncing through Frappe's /login route.
	context.login_url = (frappe.conf.get("login_url") or "").strip()
	context.desk_url = (frappe.conf.get("desk_url") or "").strip()
