"""New Relic APM enrichment for Frappe HTTP requests."""

from __future__ import annotations

import json

import frappe


def record_custom_event(event_type: str, attributes: dict | None = None) -> None:
	"""Record a New Relic custom business event."""
	try:
		import newrelic.agent
	except ImportError:
		return

	params: dict = {}
	site = getattr(frappe.local, "site", None)
	if site:
		params["frappe.site"] = site

	if attributes:
		for key, value in attributes.items():
			if value is None:
				continue
			if isinstance(value, (dict, list, tuple)):
				value = json.dumps(value)
			params[key] = value

	try:
		newrelic.agent.record_custom_event(event_type, params)
	except Exception:
		frappe.logger("core.observability").error(
			"Failed to record NR custom event %s", event_type, exc_info=True
		)


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
	request_body = getattr(request, "get_data", None)
	request_body = request_body.decode("utf-8") if request_body else None
	
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
	if request_body:
		newrelic.agent.add_custom_attribute("request.body", request_body)

	form_dict = getattr(frappe.local, "form_dict", None) or {}
	cmd = form_dict.get("cmd") if hasattr(form_dict, "get") else None
	if cmd:
		newrelic.agent.add_custom_attribute("frappe.cmd", cmd)
		newrelic.agent.set_transaction_name(f"/api/method/{cmd}", "WebTransaction")
	elif path:
		newrelic.agent.set_transaction_name(path, "WebTransaction")
