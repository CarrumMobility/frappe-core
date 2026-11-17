"""Unit tests for core.observability (no site or collector needed)."""

import datetime
import os
import unittest
from unittest import mock

import frappe
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.sampling import Decision
from opentelemetry.trace import NonRecordingSpan, SpanContext, SpanKind, TraceFlags

from core.observability import otel, otel_gunicorn, otel_jobs


def _known():
	pass


_known.__module__ = "core.api.sample"
_known.__name__ = "known"


def _login():
	pass


_login.__module__ = "frappe.handler"
_login.__name__ = "login"


class TestEnabled(unittest.TestCase):
	def test_only_otel_turns_it_on(self):
		for value, expected in [
			("otel", True),
			(" OTEL ", True),
			("newrelic", False),
			("off", False),
			("", False),
		]:
			with mock.patch.dict(os.environ, {"OBSERVABILITY": value}):
				self.assertEqual(otel.enabled(), expected, value)

	def test_unset_is_off(self):
		with mock.patch.dict(os.environ):
			os.environ.pop("OBSERVABILITY", None)
			self.assertFalse(otel.enabled())
			# The job hook must not set anything up.
			with mock.patch.object(otel, "init_providers") as init:
				otel_jobs.before_job(method="x.y")
			init.assert_not_called()
			self.assertEqual(otel_jobs._open_spans, [])


class TestSamplingRatio(unittest.TestCase):
	def test_valid_and_invalid_values(self):
		for raw, expected in [
			("0.05", 0.05),
			("0", 0.0),
			("1", 1.0),
			("5", 1.0),
			("-1", 1.0),
			("abc", 1.0),
			("nan", 1.0),
		]:
			with mock.patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": raw}):
				self.assertEqual(otel._sampling_ratio(), expected, raw)

	def test_out_of_range_does_not_raise(self):
		with mock.patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "5"}):
			otel._sampler()

	def test_remote_sampled_parent_cannot_force_sampling(self):
		with mock.patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "0"}):
			sampler = otel._sampler()
		remote = SpanContext(
			trace_id=0x1234, span_id=0x5678, is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED)
		)
		parent = trace.set_span_in_context(NonRecordingSpan(remote))
		result = sampler.should_sample(parent, 0x1234, "GET /", SpanKind.SERVER)
		self.assertEqual(result.decision, Decision.DROP)

	def test_local_sampled_parent_is_followed(self):
		with mock.patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "0"}):
			sampler = otel._sampler()
		local = SpanContext(
			trace_id=0x1234, span_id=0x5678, is_remote=False, trace_flags=TraceFlags(TraceFlags.SAMPLED)
		)
		parent = trace.set_span_in_context(NonRecordingSpan(local))
		result = sampler.should_sample(parent, 0x1234, "SELECT", SpanKind.CLIENT)
		self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)


class TestBoundedRoute(unittest.TestCase):
	def setUp(self):
		patcher = mock.patch.object(frappe, "whitelisted", [_known, _login], create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_successful_request_keeps_its_route(self):
		self.assertEqual(
			otel.bounded_route("/api/method/anything.at.all", 200), "/api/method/anything.at.all"
		)
		self.assertEqual(otel.bounded_route("/some/page", 302), "/some/page")

	def test_failed_known_method_keeps_its_route(self):
		self.assertEqual(
			otel.bounded_route("/api/method/core.api.sample.known", 500), "/api/method/core.api.sample.known"
		)
		self.assertEqual(otel.bounded_route("/api/method/login", 401), "/api/method/login")

	def test_failed_unknown_method_is_collapsed(self):
		for status in (403, 404, 417, 500):
			self.assertEqual(otel.bounded_route("/api/method/zz.random", status), "/api/method/{unknown}")
		self.assertEqual(otel.bounded_route("/api/v2/method/zz.random", 404), "/api/v2/method/{unknown}")

	def test_not_found_pages_are_collapsed(self):
		self.assertEqual(otel.bounded_route("/qwertyuiop", 404), "/{not_found}")
		self.assertEqual(otel.bounded_route("/api/resource/Zzz/{name}", 404), "/api/{not_found}")
		self.assertEqual(otel.bounded_route("/app/zzz/{name}", 404), "/app/{not_found}")

	def test_other_errors_keep_their_route(self):
		self.assertEqual(otel.bounded_route("/api/resource/Lead/{name}", 403), "/api/resource/Lead/{name}")

	def test_cache_follows_new_methods(self):
		self.assertEqual(
			otel.bounded_route("/api/method/core.api.sample.later", 500), "/api/method/{unknown}"
		)

		def later():
			pass

		later.__module__ = "core.api.sample"
		frappe.whitelisted.append(later)
		self.assertEqual(
			otel.bounded_route("/api/method/core.api.sample.later", 500), "/api/method/core.api.sample.later"
		)


class TestGunicornHook(unittest.TestCase):
	def test_post_fork_survives_setup_failure(self):
		server = mock.Mock()
		with mock.patch.object(otel, "init_providers", side_effect=ValueError("bad config")):
			otel_gunicorn.post_fork(server, mock.Mock())
		server.log.exception.assert_called_once()


class TestJobHooks(unittest.TestCase):
	def setUp(self):
		self.provider = TracerProvider()
		self.ended = []
		outer = self

		class Collect(SpanProcessor):
			def on_end(self, span):
				outer.ended.append(span)

		self.provider.add_span_processor(Collect())
		for target in [
			mock.patch.dict(os.environ, {"OBSERVABILITY": "otel"}),
			mock.patch.object(otel, "instrument_libraries"),
			mock.patch.object(otel, "init_providers"),
			mock.patch("core.observability.error_logging.install_error_logging"),
			mock.patch("core.observability.logging.install_log_compat"),
			mock.patch.object(trace, "get_tracer", self.provider.get_tracer),
			mock.patch.object(otel_jobs, "_running_in_rq_worker", return_value=False),
		]:
			target.start()
			self.addCleanup(target.stop)
		otel_jobs._open_spans.clear()

	def test_span_is_ended_when_attributes_fail(self):
		with mock.patch.object(otel_jobs, "_set_job_attributes", side_effect=TypeError("boom")):
			otel_jobs.before_job(method="core.jobs.run")
		self.assertEqual(len(otel_jobs._open_spans), 1)
		otel_jobs.after_job(method="core.jobs.run")
		self.assertEqual(otel_jobs._open_spans, [])
		self.assertEqual([s.name for s in self.ended], ["job core.jobs.run"])

	def test_wait_time_with_naive_and_aware_enqueued_at(self):
		utc = datetime.UTC
		for enqueued in (
			datetime.datetime.now(utc).replace(tzinfo=None) - datetime.timedelta(seconds=2),
			datetime.datetime.now(utc) - datetime.timedelta(seconds=2),
		):
			job = mock.Mock(id="j1", origin="short", enqueued_at=enqueued)
			with mock.patch.object(otel_jobs, "_current_rq_job", return_value=job):
				otel_jobs.before_job(method="core.jobs.run")
				otel_jobs.after_job(method="core.jobs.run")
			wait = self.ended[-1].attributes["frappe.job.wait_ms"]
			self.assertTrue(1500 <= wait <= 10000, wait)

	def test_log_level_reaches_existing_loggers(self):
		import logging

		existing = logging.getLogger("test_otel.existing")
		existing.setLevel(logging.ERROR)
		with (
			mock.patch.object(frappe, "loggers", {"x": existing}, create=True),
			mock.patch.object(frappe, "log_level", None, create=True),
		):
			otel_jobs._apply_log_level(None)
			self.assertEqual(existing.level, logging.ERROR)
			otel_jobs._apply_log_level(logging.INFO)
			self.assertEqual(existing.level, logging.INFO)
			self.assertEqual(frappe.log_level, logging.INFO)

	def test_configured_log_level(self):
		import logging

		for raw, expected in [
			("info", logging.INFO),
			("WARNING", logging.WARNING),
			("nope", None),
			("", None),
		]:
			with mock.patch.dict(os.environ, {"FRAPPE_LOG_LEVEL": raw}):
				self.assertEqual(otel.configured_log_level(), expected, raw)


if __name__ == "__main__":
	unittest.main()
