"""OpenTelemetry WSGI entry point for Frappe / gunicorn.

Sends traces and logs to the Grafana stack. Started by erpnext-config as:

    gunicorn ... --config python:core.observability.otel_gunicorn core.wsgi_otel:application

Exporter, sampler and service name come from the OTEL_* environment
variables. See core.observability.otel for why setup is split across the
gunicorn master and workers.
"""

import logging
import os

from core.observability import otel
from core.observability.error_logging import install_error_logging
from core.observability.logging import install_log_compat

# Put the final message and full tracebacks on log records for the export.
install_log_compat()
install_error_logging()

# Patch PyMySQL, Redis, requests, botocore and logging before Frappe imports
# them, so every worker inherits the patches through the fork.
otel.instrument_libraries()

import frappe
import frappe.app

# Frappe defaults to ERROR in production, which would hide WARNING/INFO from
# the log export.
_log_level_name = os.environ.get("FRAPPE_LOG_LEVEL", "DEBUG").upper()
frappe.log_level = getattr(logging, _log_level_name, logging.DEBUG)

application = otel.wrap_wsgi(frappe.app.application)
