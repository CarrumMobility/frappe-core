"""Gunicorn hooks for OpenTelemetry.

Loaded with ``gunicorn --config python:core.observability.otel_gunicorn``.
Because gunicorn runs with ``--preload``, the tracer and logger providers
must be created in each worker after the fork, not in the master.
"""


def post_fork(server, worker):
	# A telemetry problem (bad OTEL_* value, exporter import error) must not
	# stop the worker from booting: the site stays up, only without traces.
	try:
		from core.observability import otel

		otel.init_providers()
	except Exception:
		server.log.exception("OpenTelemetry setup failed; this worker runs without traces and log export")


def worker_exit(server, worker):
	from core.observability import otel

	otel.shutdown()
