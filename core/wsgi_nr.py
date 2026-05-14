"""
New Relic WSGI wrapper for Frappe / gunicorn.

Gunicorn entry point (via newrelic-admin):
    newrelic-admin run-program gunicorn ... core.wsgi_nr:application

Why both newrelic-admin AND WSGIApplicationWrapper?
- newrelic-admin: instruments Python's logging module so NR log forwarding
  captures application logs (not just gunicorn lifecycle logs).
- WSGIApplicationWrapper: explicitly wraps the WSGI callable to create web
  transactions — required because gunicorn >= 22 changed internals and
  NR's automatic gunicorn hook no longer reliably wraps the app.

All config (license key, app name, log forwarding, etc.) is sourced from
environment variables injected by Docker Compose / .env file.
"""

import newrelic.agent

# initialize() is idempotent — safe to call even when newrelic-admin
# has already initialised the agent (the second call is a no-op).
newrelic.agent.initialize()

# Import Frappe's WSGI callable AFTER NR is initialised so that all
# framework patches are applied to the imported modules.
import frappe.app  # noqa: E402

# Wrap the Frappe WSGI app so every inbound HTTP request becomes a
# New Relic web transaction with full distributed tracing context.
application = newrelic.agent.WSGIApplicationWrapper(frappe.app.application)
