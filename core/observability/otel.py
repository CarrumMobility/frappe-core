"""OpenTelemetry traces and logs for Frappe (web process and background jobs).

The web process loads it through ``core.wsgi_otel`` and background jobs
through core.observability.otel_jobs. Nothing in this module does anything
until one of those imports it.

Gunicorn runs with ``--preload``: the app is imported once in the master and
then forked. Export threads do not survive a fork, so setup is split in two:

- ``instrument_libraries()`` runs in the master at import time. It only
  patches libraries (PyMySQL, Redis, requests, botocore, logging); the patches
  look up the tracer provider lazily on every call.
- ``init_providers()`` runs in each worker after the fork
  (``core.observability.otel_gunicorn.post_fork``) and installs the tracer and
  logger providers with their own export threads.

Everything is configured through the standard ``OTEL_*`` environment
variables (service name, resource attributes, endpoint, sampling ratio in
OTEL_TRACES_SAMPLER_ARG). See _sampler() for how traces are started.
"""

from __future__ import annotations

import logging
import os
import re

from opentelemetry import trace

_LOG = logging.getLogger(__name__)

_libraries_instrumented = False
_providers_initialized = False
_otel_log_handler = None

# Paths that are never traced: the load balancer and deploy health check.
_DEFAULT_EXCLUDED_PATHS = "/api/method/ping"

# Path segments that look like record names or IDs are replaced so routes stay
# low-cardinality in span metrics (one series per route, not per document).
_API_VERSION = re.compile(r"^v\d+$")
_HEX_ID = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)


def _looks_like_id(segment: str) -> bool:
	if _API_VERSION.match(segment):
		return False
	return any(c.isdigit() for c in segment) or bool(_HEX_ID.match(segment))


# ---------------------------------------------------------------- setup


def instrument_libraries() -> None:
	"""Patch client libraries so their calls become child spans. Idempotent."""
	global _libraries_instrumented
	if _libraries_instrumented:
		return

	from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
	from opentelemetry.instrumentation.logging import LoggingInstrumentor
	from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor
	from opentelemetry.instrumentation.redis import RedisInstrumentor
	from opentelemetry.instrumentation.requests import RequestsInstrumentor

	PyMySQLInstrumentor().instrument()
	RedisInstrumentor().instrument()
	RequestsInstrumentor().instrument()
	BotocoreInstrumentor().instrument()
	# Adds otelTraceID / otelSpanID to every LogRecord (stdout logs included).
	LoggingInstrumentor().instrument(set_logging_format=False)

	_patch_frappe_exceptions()
	_libraries_instrumented = True


def init_providers() -> None:
	"""Install tracer + logger providers in this process. Idempotent."""
	global _providers_initialized, _otel_log_handler
	if _providers_initialized:
		return

	from opentelemetry._logs import set_logger_provider
	from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
	from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
	from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
	from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
	from opentelemetry.sdk.resources import Resource
	from opentelemetry.sdk.trace import TracerProvider
	from opentelemetry.sdk.trace.export import BatchSpanProcessor

	# Resource.create() merges OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES.
	resource = Resource.create({"service.namespace": "carrum"})

	tracer_provider = TracerProvider(resource=resource, sampler=_sampler())
	tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
	trace.set_tracer_provider(tracer_provider)

	logger_provider = LoggerProvider(resource=resource)
	logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
	set_logger_provider(logger_provider)

	level_name = os.environ.get("FRAPPE_LOG_LEVEL", "WARNING").upper()
	_otel_log_handler = LoggingHandler(
		level=getattr(logging, level_name, logging.WARNING), logger_provider=logger_provider
	)
	_attach_log_handler()

	_providers_initialized = True


def flush(timeout_millis: int = 5000) -> None:
	"""Export buffered spans and logs now (end of a forked RQ job)."""
	if not _providers_initialized:
		return
	try:
		from opentelemetry._logs import get_logger_provider

		trace.get_tracer_provider().force_flush(timeout_millis)
		get_logger_provider().force_flush(timeout_millis)
	except Exception:
		_LOG.debug("OpenTelemetry flush failed", exc_info=True)


def _sampler():
	"""ParentBased(trace-id ratio), but never start a trace from a bare client span.

	SQL, Redis and HTTP calls made outside a request or job (health checks,
	which skip the WSGI span on purpose, worker start-up, the scheduler loop)
	would otherwise each become a one-span trace. Spans with a parent follow
	the parent's decision as usual. The ratio comes from OTEL_TRACES_SAMPLER_ARG.
	"""
	from opentelemetry.sdk.trace.sampling import (
		Decision,
		ParentBased,
		Sampler,
		SamplingResult,
		TraceIdRatioBased,
	)
	from opentelemetry.trace import SpanKind

	try:
		ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
	except ValueError:
		ratio = 1.0

	class _RootFilter(Sampler):
		def __init__(self, delegate):
			self._delegate = delegate

		def should_sample(
			self, parent_context, trace_id, name, kind=None, attributes=None, links=None, trace_state=None
		):
			if kind in (SpanKind.CLIENT, SpanKind.PRODUCER, SpanKind.INTERNAL):
				return SamplingResult(Decision.DROP)
			return self._delegate.should_sample(
				parent_context, trace_id, name, kind, attributes, links, trace_state
			)

		def get_description(self):
			return f"RootFilter({self._delegate.get_description()})"

	return ParentBased(root=_RootFilter(TraceIdRatioBased(ratio)))


def shutdown() -> None:
	"""Flush buffered spans and logs (gunicorn worker exit)."""
	if not _providers_initialized:
		return
	try:
		from opentelemetry._logs import get_logger_provider

		trace.get_tracer_provider().shutdown()
		get_logger_provider().shutdown()
	except Exception:
		_LOG.debug("OpenTelemetry shutdown failed", exc_info=True)


def _attach_log_handler() -> None:
	"""Send records from the root logger and every Frappe logger to OTLP.

	Frappe's loggers set ``propagate = False``, so a root handler alone would
	miss them. Loggers created later are covered by wrapping get_logger.
	"""
	logging.getLogger().addHandler(_otel_log_handler)

	import frappe
	from frappe.utils import logger as frappe_logger

	for existing in list(getattr(frappe, "loggers", {}).values()):
		_add_handler(existing)

	original_get_logger = frappe_logger.get_logger
	if getattr(original_get_logger, "_otel_wrapped", False):
		return

	def get_logger(*args, **kwargs):
		result = original_get_logger(*args, **kwargs)
		_add_handler(result)
		return result

	get_logger._otel_wrapped = True
	frappe_logger.get_logger = get_logger
	frappe.logger = get_logger


def _add_handler(target: logging.Logger) -> None:
	if _otel_log_handler is not None and _otel_log_handler not in target.handlers:
		target.addHandler(_otel_log_handler)


def _patch_frappe_exceptions() -> None:
	"""Record unhandled request exceptions on the server span.

	Frappe turns exceptions into responses inside ``frappe.app.application``,
	so the WSGI middleware only sees a status code. This keeps the exception
	type, message and stack trace on the trace.
	"""
	import frappe.app

	original = frappe.app.handle_exception
	if getattr(original, "_otel_wrapped", False):
		return

	def handle_exception(e):
		span = trace.get_current_span()
		if span.is_recording():
			span.record_exception(e)
		return original(e)

	handle_exception._otel_wrapped = True
	frappe.app.handle_exception = handle_exception


# ---------------------------------------------------------------- WSGI


def wrap_wsgi(app):
	"""Wrap a WSGI app so each request becomes a server span."""
	from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

	traced = OpenTelemetryMiddleware(app, request_hook=_request_hook)
	excluded = {
		p.strip()
		for p in os.environ.get("OTEL_EXCLUDED_PATHS", _DEFAULT_EXCLUDED_PATHS).split(",")
		if p.strip()
	}

	def application(environ, start_response):
		if environ.get("PATH_INFO") in excluded:
			return app(environ, start_response)
		return traced(environ, start_response)

	return application


def _request_hook(span, environ) -> None:
	if not span.is_recording():
		return
	route = route_template(environ.get("PATH_INFO") or "/")
	span.set_attribute("http.route", route)
	span.update_name(f"{environ.get('REQUEST_METHOD', 'GET')} {route}")


def route_template(path: str) -> str:
	"""Turn a Frappe URL into a low-cardinality route.

	/api/method/<dotted.path>        kept as is (the method is the route)
	/api/resource/<DocType>/<name>   -> /api/resource/<DocType>/{name}
	/api/v2/document/<DocType>/<id>  -> /api/v2/document/<DocType>/{name}
	/app/<doctype>/<name>            -> /app/<doctype>/{name}
	/files/<file>, /private/files/.. -> /files/{file}
	anything else: ID-looking segments become {id}
	"""
	parts = [p for p in path.split("/") if p]
	if not parts:
		return "/"

	if parts[0] == "api":
		if len(parts) >= 3 and parts[1] == "method":
			return "/api/method/" + "/".join(parts[2:])
		if len(parts) >= 4 and parts[1] == "v2" and parts[2] == "method":
			return "/api/v2/method/" + "/".join(parts[3:])
		if len(parts) >= 4 and parts[1] == "resource":
			return f"/api/resource/{parts[2]}/{{name}}"
		if len(parts) >= 5 and parts[1] == "v2" and parts[2] == "document":
			return f"/api/v2/document/{parts[3]}/{{name}}"

	if parts[0] == "app" and len(parts) >= 3:
		return f"/app/{parts[1]}/{{name}}"
	if parts[0] == "files":
		return "/files/{file}"
	if parts[:2] == ["private", "files"]:
		return "/private/files/{file}"

	return "/" + "/".join("{id}" if _looks_like_id(p) else p for p in parts)


# ---------------------------------------------------------------- Frappe hook


def enrich_span(response, request) -> None:
	"""after_request hook: attach Frappe context to the current server span.

	Does nothing when OpenTelemetry is not active (no recording span).
	"""
	span = trace.get_current_span()
	if not span.is_recording():
		return

	try:
		import frappe

		site = getattr(frappe.local, "site", None)
		user = getattr(getattr(frappe.local, "session", None), "user", None)
		if site:
			span.set_attribute("frappe.site", site)
		if user:
			span.set_attribute("enduser.id", user)

		form_dict = getattr(frappe.local, "form_dict", None) or {}
		cmd = form_dict.get("cmd") if hasattr(form_dict, "get") else None
		if cmd:
			# Old-style RPC posts to "/" with cmd in the body; name it like
			# /api/method so both styles group together.
			span.set_attribute("frappe.cmd", cmd)
			route = f"/api/method/{cmd}"
			span.set_attribute("http.route", route)
			span.update_name(f"{getattr(request, 'method', 'POST')} {route}")

		if os.environ.get("OTEL_CAPTURE_REQUEST_BODY", "").lower() in ("1", "true", "yes"):
			from core.observability.request_logging import format_request_body

			body = format_request_body(request, max_length=4000) if request is not None else ""
			if body:
				span.set_attribute("http.request.body", body)
	except Exception:
		_LOG.debug("Could not enrich span", exc_info=True)
