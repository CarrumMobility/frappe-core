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

import logging
import json
import os

import newrelic.agent

# ---------------------------------------------------------------------------
# Stringify dict log messages for New Relic log forwarding.
#
# Frappe's log_request() and other code pass dicts as log messages:
#   logger.info({"site": "...", "user": "...", ...})
#
# NR's callHandlers hook checks `isinstance(record.msg, dict)` — when True,
# it passes the raw dict to record_log_event() which stores keys as attributes
# but leaves the displayed message field EMPTY in the NR Logs UI.
#
# Fix: use a custom LogRecord factory to convert dict messages into readable
# strings at record creation time — before NR's hook ever sees them.
# ---------------------------------------------------------------------------
_original_record_factory = logging.getLogRecordFactory()


def _format_request_dict(d):
    """Format Frappe's request log dict into a human-readable line.

    Example output:
        POST /api/method/crm.api.lead.get_lead → 200 user=Administrator site=erp-v3.carrum.co.in
    """
    method = d.get("method", "")
    path = d.get("full_path", d.get("base_url", ""))
    status = d.get("http_status_code", "")
    user = d.get("user", "")
    body = d.get("body", {})

    # site = d.get("site", "")
    # remote = d.get("remote_addr", "")

    # Build a concise request log line
    parts = []
    if method and path:
        parts.append(f"{method} {path}")
    if status:
        parts.append(f"→ {status}")
    if user:
        parts.append(f"user={user}")
    if body:
        parts.append(f"body={_format_body(body)}")
    return " ".join(parts) if parts else json.dumps(d, default=str)

def _format_body(body):
    return json.dumps(body, default=str)


def _nr_record_factory(*args, **kwargs):
    record = _original_record_factory(*args, **kwargs)
    if isinstance(record.msg, dict):
        d = record.msg
        # Frappe request logs have 'full_path' and 'method' keys
        if "full_path" in d or "method" in d:
            record.msg = _format_request_dict(d)
        else:
            record.msg = json.dumps(d, default=str)
        record.args = None
    return record


logging.setLogRecordFactory(_nr_record_factory)

# initialize() is idempotent — safe to call even when newrelic-admin
# has already initialised the agent (the second call is a no-op).
newrelic.agent.initialize()

# Import Frappe's WSGI callable AFTER NR is initialised so that all
# framework patches are applied to the imported modules.
import frappe  # noqa: E402
import frappe.app  # noqa: E402

# ---------------------------------------------------------------------------
# Frappe log level override for the web (gunicorn) process.
#
# By default Frappe sets log level to ERROR in production (non-dev-server),
# which means only ERROR/CRITICAL messages are emitted — way too restrictive
# for observability.  We lower it here so NR log forwarding (which hooks
# logging.Logger.callHandlers) can capture WARNING/INFO logs as well.
#
# Configurable via FRAPPE_LOG_LEVEL env var (default: INFO).
# ---------------------------------------------------------------------------
_log_level_name = os.environ.get("FRAPPE_LOG_LEVEL", "INFO").upper()
frappe.log_level = getattr(logging, _log_level_name, logging.INFO)

# Wrap the Frappe WSGI app so every inbound HTTP request becomes a
# New Relic web transaction with full distributed tracing context.
application = newrelic.agent.WSGIApplicationWrapper(frappe.app.application)
