"""OpenTelemetry spans for Frappe background jobs (RQ workers).

Wired through Frappe's ``before_job`` / ``after_job`` hooks, which
``frappe.utils.background_jobs.execute_job`` calls around every job (the same
hooks Frappe's own monitor uses). Only active with ``OBSERVABILITY=otel``; otherwise
both hooks return at once.

RQ's default worker forks a fresh process per job and ends it with
``os._exit``, which skips the exporters' background flush. So each job
process sets up OpenTelemetry on its first job and flushes when the job
finishes. Jobs run inline from a web request (``enqueue(..., now=True)``)
become child spans of that request and are flushed with it instead.

Deadlock retries call ``execute_job`` again before the outer call's
``after_job`` runs, so spans are kept on a stack rather than in frappe.local
(which ``frappe.destroy()`` clears between retries).
"""

from __future__ import annotations

import logging
import sys

from opentelemetry import context, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_LOG = logging.getLogger(__name__)
_TRACER_NAME = "core.observability.jobs"
_SCHEDULED_JOB_METHOD = "frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job"

_open_spans: list = []  # (span, context token), innermost last


def _enabled() -> bool:
	from core.observability import otel

	return otel.enabled()


def before_job(method=None, kwargs=None, transaction_type=None) -> None:
	if not _enabled():
		return
	try:
		from core.observability import otel
		from core.observability.error_logging import install_error_logging
		from core.observability.logging import install_log_compat

		# hooks.py runs these only in the process that builds the hooks cache,
		# so a job process usually has not. Both are idempotent.
		install_log_compat()
		install_error_logging()
		otel.instrument_libraries()
		otel.init_providers()
		_apply_log_level(otel.configured_log_level())

		# Scheduled jobs all run through one generic method; name them after
		# the real job (same rule as frappe.monitor).
		scheduled_type = None
		if method and _SCHEDULED_JOB_METHOD in method:
			scheduled_type = (kwargs or {}).get("job_type") or method
		name = f"scheduled {scheduled_type}" if scheduled_type else f"job {method}"

		span = trace.get_tracer(_TRACER_NAME).start_span(name, kind=SpanKind.CONSUMER)
		# Attach first: once the span is on the stack after_job always ends
		# it, whatever happens while the attributes are filled in.
		token = context.attach(trace.set_span_in_context(span))
		_open_spans.append((span, token))
	except Exception:
		_LOG.warning("Could not start job span", exc_info=True)
		return

	try:
		if span.is_recording():
			_set_job_attributes(span, method)
			if scheduled_type:
				span.set_attribute("frappe.job.scheduled", True)
				span.set_attribute("frappe.job.type", scheduled_type)
	except Exception:
		_LOG.warning("Could not set job span attributes", exc_info=True)


def after_job(method=None, kwargs=None, result=None) -> None:
	if not _enabled() or not _open_spans:
		return
	span, token = _open_spans.pop()
	try:
		# after_job runs in execute_job's `finally`, so a failing job's
		# exception is still the one being handled here.
		error = sys.exc_info()[1]
		if error is not None:
			span.record_exception(error)
			span.set_status(Status(StatusCode.ERROR, f"{type(error).__name__}: {error}"))
		span.end()
	finally:
		context.detach(token)

	if not _open_spans and _running_in_rq_worker():
		from core.observability import otel

		otel.flush()


def _set_job_attributes(span, method) -> None:
	import frappe

	span.set_attribute("frappe.job.method", method or "")
	site = getattr(frappe.local, "site", None)
	if site:
		span.set_attribute("frappe.site", site)
	user = getattr(getattr(frappe.local, "session", None), "user", None)
	if user:
		span.set_attribute("enduser.id", user)

	job = _current_rq_job()
	if job is None:
		return
	span.set_attribute("messaging.system", "rq")
	span.set_attribute("messaging.message.id", job.id)
	if job.origin:
		span.set_attribute("messaging.destination.name", job.origin)
	if job.enqueued_at is not None:
		import datetime

		# rq 1.x gives a naive UTC datetime, rq 2.x an aware one.
		utc = datetime.UTC
		enqueued = job.enqueued_at
		enqueued = enqueued.replace(tzinfo=utc) if enqueued.tzinfo is None else enqueued
		wait = datetime.datetime.now(utc) - enqueued
		span.set_attribute("frappe.job.wait_ms", int(wait.total_seconds() * 1000))


def _apply_log_level(level: int | None) -> None:
	"""Let FRAPPE_LOG_LEVEL reach job logs, as core.wsgi_otel does for web.

	Frappe caps its loggers at ERROR outside developer mode, and a logger
	keeps the level it was created with, so the ones that already exist are
	lowered too. Without the variable nothing changes.
	"""
	if level is None:
		return
	import frappe

	frappe.log_level = level
	for existing in list(getattr(frappe, "loggers", {}).values()):
		existing.setLevel(level)


def _current_rq_job():
	try:
		import rq

		return rq.get_current_job()
	except Exception:
		return None


def _running_in_rq_worker() -> bool:
	return _current_rq_job() is not None
