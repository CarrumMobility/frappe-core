# Observability — Technical Documentation

**Module:** `core.observability`  
**App:** `core`  
**Status:** Live  
**Backend:** OpenTelemetry → Grafana stack (Alloy, Tempo, Loki, Prometheus, Grafana) in GCP project `carrum-mgmt`

---

## Overview

The `core` app sends traces, logs and business events from Frappe processes with OpenTelemetry (OTLP over HTTP), and browser telemetry from the Desk with Grafana Faro.

Design goals:

1. **Request and job context on traces, not log spam** — site, user and command go on the span.
2. **Complete error visibility** — Frappe errors emit full tracebacks to logs, linked to the trace by `trace_id`.
3. **Readable log export** — dict- and `%`-formatted messages are materialized before export.
4. **Background coverage** — every queue and scheduled job is a trace.
5. **Low cardinality** — routes are templated; bare client spans never start a trace.
6. **Safe defaults** — SQL values never recorded; request bodies off unless enabled, then redacted and truncated.

---

## Architecture

```mermaid
flowchart TB
    subgraph Web process - gunicorn --preload
        WSGI[core.wsgi_otel:application]
        GC[otel_gunicorn.post_fork]
        MW[WSGI middleware - server span]
        AR[after_request: otel.enrich_span]
        WSGI --> MW --> AR
        GC -. providers per worker .-> MW
    end

    subgraph Worker process - RQ, fork per job
        BJ[before_job: otel_jobs.before_job]
        AJ[after_job: otel_jobs.after_job + flush]
    end

    subgraph Libraries
        LIB[PyMySQL, redis, requests, botocore, logging]
    end

    subgraph Desk
        FARO[faro_init.js] -->|boot info| BOOT[faro.boot_session]
    end

    MW --> LIB
    BJ --> LIB
    MW -->|OTLP| ALLOY[Alloy otel.obs.internal:4318]
    AJ -->|OTLP| ALLOY
    FARO -->|HTTPS| FAROEP[faro.carrum.co.in/collect]
    EV[events.record_event] -->|OTLP log| ALLOY
```

---

## Code layout

| Path | Purpose |
|---|---|
| `core/wsgi_otel.py` | Gunicorn WSGI entry point: installs log helpers, instruments libraries, wraps `frappe.app.application` |
| `core/observability/otel.py` | Providers, sampler, route templating, exception recording, `enrich_span`, log handler wiring, `flush()` |
| `core/observability/otel_gunicorn.py` | `post_fork` / `worker_exit` hooks (`--config python:core.observability.otel_gunicorn`) |
| `core/observability/otel_jobs.py` | `before_job` / `after_job` hooks: one CONSUMER span per job |
| `core/observability/events.py` | `record_event()` — business events as OTLP log records |
| `core/observability/faro.py` | `boot_session` — passes Faro settings to the Desk |
| `core/public/js/faro_init.js` | Loads Faro 2.12.1 (jsDelivr, SRI) when boot info has `faro` |
| `core/observability/logging.py` | Log record factory that materializes messages |
| `core/observability/error_logging.py` | Patches `frappe.log_error` / `log_error_snapshot` for full tracebacks |
| `core/observability/request_logging.py` | Request body serialization, redaction, truncation |
| `core/api/observability/observability.py` | Whitelisted `track_lead_views` API for the CRM frontend |

Dependencies (`pyproject.toml`): `opentelemetry-sdk` 1.45.1, `opentelemetry-exporter-otlp-proto-http` 1.45.1 and instrumentations 0.66b1 (wsgi, pymysql, redis, requests, botocore, logging). SDK and contrib versions move together.

---

## Hook registration (`core/hooks.py`)

```python
# Module import time, in the process that builds the hooks cache
install_log_compat()
install_error_logging()

app_include_js = ["/assets/core/js/faro_init.js"]
boot_session = "core.observability.faro.boot_session"

before_job = ["core.observability.otel_jobs.before_job"]
after_job = ["core.observability.otel_jobs.after_job"]

after_request = ["core.observability.otel.enrich_span"]
```

Frappe caches hooks in Redis, so the module-level installs do not run in every process. `wsgi_otel.py` and `otel_jobs.before_job` call both installs themselves; they are idempotent.

---

## Web process

Started by erpnext-config:

```bash
gunicorn ... --preload --config python:core.observability.otel_gunicorn core.wsgi_otel:application
```

- **`--preload`**: the app is imported in the master and forked. Library instrumentation is applied in the master (it resolves the tracer provider lazily); tracer and logger providers, with their export threads, are created in each worker in `post_fork`.
- **Span names and routes**: `/api/method/<method>` as is; `/api/resource/<DocType>/{name}`, `/api/v2/document/<DocType>/{name}`, `/app/<doctype>/{name}`, `/files/{file}`; other ID-like segments become `{id}`. Old-style `POST /` with `cmd` is renamed to `/api/method/<cmd>` in `enrich_span`.
- **Attributes**: `frappe.site`, `enduser.id`, `frappe.cmd`, plus HTTP semantic conventions from the middleware. `OTEL_CAPTURE_REQUEST_BODY=true` adds a redacted, truncated `http.request.body` (off by default).
- **Exceptions**: `frappe.app.handle_exception` is wrapped to record the exception on the server span.
- **Excluded paths**: `OTEL_EXCLUDED_PATHS` (default `/api/method/ping`) skip the server span.

## Background jobs

`frappe.utils.background_jobs.execute_job` calls `before_job` before and `after_job` in its `finally` for every job.

- RQ's default worker forks a process per job and ends it with `os._exit`, which skips background export. Each job process initializes OpenTelemetry on first use and `after_job` calls `otel.flush()` (5 s timeout) when running under RQ.
- Span: `job <method>` or, for scheduled jobs (`run_scheduled_job`), `scheduled <job_type>`; kind CONSUMER; service `<OTEL_SERVICE_NAME>` (erpnext-config sets `erpnext-worker`).
- Attributes: `frappe.job.method`, `frappe.site`, `enduser.id`, `messaging.system=rq`, `messaging.message.id`, `messaging.destination.name` (queue), `frappe.job.wait_ms`, `frappe.job.scheduled`, `frappe.job.type`.
- Failures: `after_job` runs in `finally`, so `sys.exc_info()` still holds the job's exception; it is recorded and the span status set to ERROR.
- Deadlock retries call `execute_job` recursively; spans are kept on a module-level stack because `frappe.destroy()` clears `frappe.local` between attempts.

## Sampling

`ParentBased(TraceIdRatioBased(OTEL_TRACES_SAMPLER_ARG))`, with one rule for roots: a CLIENT, PRODUCER or INTERNAL span with no parent is dropped. Without it, SQL/Redis calls outside a request or job (health checks, worker start-up, the scheduler loop) each become a one-span trace.

## Logs

A `LoggingHandler` is attached to the root logger and to every Frappe logger (they set `propagate = False`; `frappe.utils.logger.get_logger` is wrapped to cover loggers created later). Handler level follows `FRAPPE_LOG_LEVEL`. Each record carries the active `trace_id` / `span_id`.

`error_logging.py` makes `frappe.log_error` and `log_error_snapshot` also log:

```
Frappe log_error_snapshot [ValidationError]: Title | site=... | user=... | cmd=... | trace_id=...
<full traceback>
```

## Business events

`core.observability.events.record_event(event_type, attributes)` emits one OTLP log record through the Logs API (not a Python logger, so `FRAPPE_LOG_LEVEL` cannot drop it): body = event type, attributes = `event.name`, `frappe.site` and the given attributes (dicts/lists JSON-encoded). Query:

```logql
{service_name="erpnext"} | event_name="CrmLeadViewed"
```

Adding an event:

1. Add a constant to `EnumValues.CrmEventTypes` in `core/constants/enums.py`.
2. Call `record_event(event_type, attributes)`, or expose a whitelisted API under `core/api/observability/`.
3. Keep attributes flat; avoid PII beyond what product requires; never pass secrets.

## Desk browser monitoring

`boot_session` copies `faro_collect_url`, `faro_app_name` (default `erpnext`) and `faro_environment` from site config into `frappe.boot.faro`. `faro_init.js` then loads the Faro SDK and tracing bundles from jsDelivr with SRI and initializes web instrumentations (no console capture, no replay), ignoring `/socket.io/` and the collector URL. The tracing instrumentation adds `traceparent` to same-origin requests, so backend spans join the browser trace. Without `faro_collect_url` nothing loads.

---

## Configuration

| Variable | Set by | Notes |
|---|---|---|
| `OBSERVABILITY` | erpnext-config | `otel` (default) or `off` to disable job spans and events |
| `OTEL_SERVICE_NAME` | erpnext-config | `erpnext` (web), `erpnext-worker` (workers) |
| `OTEL_RESOURCE_ATTRIBUTES` | erpnext-config | `deployment.environment=<dev\|qa\|prod>` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | erpnext-config | `http://otel.obs.internal:4318` |
| `OTEL_TRACES_SAMPLER_ARG` | erpnext-config | Ratio of traces kept (default `1.0`) |
| `OTEL_EXCLUDED_PATHS` | erpnext-config | Comma-separated paths without a server span |
| `OTEL_CAPTURE_REQUEST_BODY` | optional | `true` to attach redacted request bodies |
| `FRAPPE_LOG_LEVEL` | erpnext-config | Log export level |

| Site config key | Purpose |
|---|---|
| `faro_collect_url` | Turns on Desk browser monitoring |
| `faro_environment`, `faro_app_name` | Faro labels |
| `api_request_body_log_max_length` | Max serialized body length in `format_request_body` (default 10 000) |

---

## Graceful degradation

- No recording span → `enrich_span` does nothing.
- `OBSERVABILITY=off` → job hooks and `record_event` return at once.
- Exporter unreachable → spans and logs are dropped after retries; requests and jobs are not affected.
- `record_event` failures are logged and never raise.

---

## Testing locally

Run the Grafana stack locally (`scripts/smoke-local.sh` with `KEEP=1` in CarrumMobility/observability-config), then start gunicorn with the command above and `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, and a worker with `bench worker`. Traces appear in Grafana at `http://localhost:3000` (Tempo), logs and events in Loki.

---

## Related documentation

- [Observability — product overview](../../product/observability/readme.md)
