"""
New Relic WSGI wrapper for Frappe / gunicorn.

Gunicorn entry point: core.wsgi_nr:application

This replaces the `newrelic-admin run-program` approach which does not
reliably instrument web transactions on modern gunicorn (>= 22).

The agent is initialised here — via environment variables only (no .ini
file required). All config (license key, app name, log forwarding, etc.)
is sourced from environment variables injected by Docker Compose from the
EC2 .env file, which is populated from AWS Secrets Manager on every deploy.
"""
import os

import newrelic.agent

# Initialise the agent from environment variables.
# Must happen before importing frappe so the agent can patch all frameworks
# (SQL, Redis, requests, etc.) before they are first imported.
newrelic.agent.initialize()

# Import Frappe's WSGI callable AFTER NR is initialised so that all
# framework patches are applied to the imported modules.
import frappe.app  # noqa: E402

# Wrap the Frappe WSGI app so every inbound HTTP request becomes a
# New Relic web transaction with full distributed tracing context.
application = newrelic.agent.WSGIApplicationWrapper(frappe.app.application)
