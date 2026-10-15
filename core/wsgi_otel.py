"""OpenTelemetry WSGI entry point for Frappe / gunicorn.

Counterpart of core.wsgi_nr for environments that send telemetry to the
Grafana stack instead of New Relic. Selected by erpnext-config with
``OBSERVABILITY=otel``:

    gunicorn ... --config python:core.observability.otel_gunicorn core.wsgi_otel:application

Exporter, sampler and service name come from the OTEL_* environment
variables. See core.observability.otel for why setup is split across the
gunicorn master and workers.
"""

import logging
import os

from core.observability import otel
from core.observability.error_logging import install_error_logging_for_newrelic
from core.observability.logging import install_newrelic_log_compat

# Despite the names, both helpers are backend-neutral: they put the final
# message and full tracebacks on log records, which the OTLP log export uses
# just as New Relic's log forwarding did.
install_newrelic_log_compat()
install_error_logging_for_newrelic()

# Patch PyMySQL, Redis, requests, botocore and logging before Frappe imports
# them, so every worker inherits the patches through the fork.
otel.instrument_libraries()

import frappe
import frappe.app

# Same log level override as core.wsgi_nr: Frappe defaults to ERROR in
# production, which would hide WARNING/INFO from the log export.
_log_level_name = os.environ.get("FRAPPE_LOG_LEVEL", "DEBUG").upper()
frappe.log_level = getattr(logging, _log_level_name, logging.DEBUG)

application = otel.wrap_wsgi(frappe.app.application)
