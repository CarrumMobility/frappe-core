"""Gunicorn hooks for OpenTelemetry.

Loaded with ``gunicorn --config python:core.observability.otel_gunicorn``.
Because gunicorn runs with ``--preload``, the tracer and logger providers
must be created in each worker after the fork, not in the master.
"""


def post_fork(server, worker):
	from core.observability import otel

	otel.init_providers()


def worker_exit(server, worker):
	from core.observability import otel

	otel.shutdown()
