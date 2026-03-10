# Copyright (c) 2025, Core and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Allow guest access so SSO page can load and perform cookie-based login."""
	context.no_cache = 1
	# redirect-to is required (from query params); no default
	context.redirect_to = frappe.form_dict.get("redirect-to") or None
