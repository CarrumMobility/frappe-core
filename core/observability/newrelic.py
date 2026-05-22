"""New Relic APM enrichment for Frappe HTTP requests."""

from __future__ import annotations

import frappe


def enrich_newrelic_transaction(response, request) -> None:
	"""Attach Frappe context to the current NR web transaction.

	Called from the after_request hook. Request metadata lives on the APM
	transaction (queryable in NR APM / NRQL) instead of per-request log lines.
	"""
	try:
		import newrelic.agent
	except ImportError:
		return

	if newrelic.agent.current_transaction() is None:
		return

	site = getattr(frappe.local, "site", None)
	user = getattr(getattr(frappe.local, "session", None), "user", None)
	status_code = getattr(response, "status_code", None)
	method = getattr(request, "method", None)
	path = getattr(request, "path", None)
	remote_addr = getattr(request, "remote_addr", None)

	if site:
		newrelic.agent.add_custom_attribute("frappe.site", site)
	if user:
		newrelic.agent.add_custom_attribute("frappe.user", user)
	if status_code is not None:
		newrelic.agent.add_custom_attribute("http.status_code", status_code)
	if method:
		newrelic.agent.add_custom_attribute("http.method", method)
	if path:
		newrelic.agent.add_custom_attribute("http.path", path)
	if remote_addr:
		newrelic.agent.add_custom_attribute("http.remote_addr", remote_addr)

	form_dict = getattr(frappe.local, "form_dict", None) or {}
	cmd = form_dict.get("cmd") if hasattr(form_dict, "get") else None
	if cmd:
		newrelic.agent.add_custom_attribute("frappe.cmd", cmd)
		newrelic.agent.set_transaction_name(f"/api/method/{cmd}", "WebTransaction")
	elif path:
		newrelic.agent.set_transaction_name(path, "WebTransaction")
