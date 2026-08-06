# New Relic Integration — Product Guide

**Feature:** Platform Monitoring  
**Status:** Live  
**Vendor:** [New Relic](https://newrelic.com/)

---

## Overview

Carrum CRM uses the **New Relic Python APM agent** to monitor the Frappe application in every environment where it is enabled. One New Relic **application** typically maps to one deployment (e.g. `FRAPPE_PROD`, `FRAPPE_DEV`).

This guide explains what appears in the New Relic UI and how non-engineers can use it for reporting and incident triage. For setup, configuration, and code references, see the [technical New Relic documentation](../../technical/observability/newrelic.md).

---

## New Relic surfaces you will use

| Surface | Purpose |
|---|---|
| **APM → Summary** | Health at a glance: throughput, error rate, Apdex |
| **APM → Transactions** | Drill into specific API methods, pages, jobs |
| **APM → Errors** | Grouped exceptions with stack traces |
| **Logs** | Search application log lines; link to traces |
| **Query (NRQL)** | Custom reports and dashboards |
| **Alerts** | Notify on error rate, latency, or custom NRQL conditions |

---

## Application naming

Each environment should report to a **distinct app name** so dev traffic does not mix with production:

| Environment | Example app name |
|---|---|
| Local / dev | `FRAPPE_KAPIL_DEV` |
| Staging | `FRAPPE_STAGING` |
| Production | `FRAPPE_PROD` |

App name is set via New Relic configuration (environment variable `NEW_RELIC_APP_NAME` or `newrelic.ini`). EU accounts use the `eu01` data region — confirm you are logged into the correct New Relic account/region.

---

## Web transaction attributes

These attributes are attached automatically to every HTTP request and can be used in NRQL filters and dashboard widgets:

| Attribute | Example | Use |
|---|---|---|
| `frappe.site` | `dev.carrum.co.in` | Multi-site bench — isolate one tenant |
| `frappe.user` | `agent@hub.com` | Reproduce user-specific issues |
| `frappe.cmd` | `crm.api.lead.get_lead` | Pinpoint a whitelisted API method |
| `http.method` | `POST` | Filter by verb |
| `http.path` | `/api/method/...` | Non-method routes |
| `http.status_code` | `500` | Find failing responses |
| `http.remote_addr` | Client IP | Geo or abuse patterns |
| `request.body` | Redacted JSON | Inspect payload shape (no secrets) |

**Transaction names** follow a predictable pattern:

- API calls: `/api/method/{dotted.method.path}`
- Other routes: the URL path (e.g. `/app/crm`)

---

## Background transaction attributes

| Group | When | Key attributes |
|---|---|---|
| **Task** | Redis queue worker jobs | `job_name`, `queue`, `frappe.site` |
| **Scheduler** | Cron-style scheduled jobs | `scheduled_job_name`, `frappe.site` |

Scheduler transactions use human-readable names such as `Scheduler Sync Facebook Leads` instead of raw Python module paths.

---

## Custom events

Custom events capture **product behavior** that APM alone cannot express.

### `CrmLeadViewed`

Recorded when an authenticated user views leads in the CRM UI.

| Field | Description |
|---|---|
| `frappe.user` | User who viewed the lead |
| `frappe.site` | Site context (added automatically) |
| `lead_id` | CRM Lead document name |
| `view_type` | `list` or `detail` |
| `route_name` | Vue route name (e.g. `Leads`, `Lead`) |

**Sources:**

- **Leads list** — batched when the list loads (up to 100 leads per request)
- **Lead detail** — single lead when the detail page opens

Guest sessions are not recorded.

### Example NRQL queries

**Lead views in the last 24 hours by view type:**

```sql
SELECT count(*) FROM CrmLeadViewed
FACET view_type
SINCE 1 day ago
```

**Most viewed leads this week:**

```sql
SELECT count(*) FROM CrmLeadViewed
FACET lead_id
SINCE 7 days ago
LIMIT 20
```

**Daily active users viewing leads:**

```sql
SELECT uniqueCount(frappe.user) FROM CrmLeadViewed
SINCE 30 days ago
TIMESERIES 1 day
```

**List vs detail split by route:**

```sql
SELECT count(*) FROM CrmLeadViewed
FACET route_name, view_type
SINCE 1 week ago
```

---

## Logs and trace correlation

When an error occurs during a web request:

1. The exception is written to Python logs with site, user, API command, and Frappe trace ID.
2. New Relic forwards the log line.
3. The log entry is **correlated** with the active APM transaction.

In the UI: open a transaction → **Logs** → see the full stack trace without opening Frappe Error Log.

This replaces the previous gap where Frappe only logged `"New Exception collected in error log"` to stdout.

---

## Suggested dashboards and alerts

### Dashboards (starting points)

1. **CRM API health** — transaction times and error rate faceted by `frappe.cmd`
2. **Per-site overview** — throughput and errors faceted by `frappe.site`
3. **Background jobs** — duration and errors for groups `Scheduler` and `Task`
4. **Lead engagement** — `CrmLeadViewed` timeseries and top users/leads

### Alert ideas

| Condition | Threshold idea |
|---|---|
| Error rate on production app | > 2% for 5 minutes |
| Specific critical API (`frappe.cmd`) | Any error in 1 minute |
| Scheduler job failures | Error count > 0 for named transaction |
| Log pattern | Message contains `Frappe log_error_snapshot` and `site=production` |

Tune thresholds per environment — dev apps are expected to be noisier.

---

## Access and permissions

- New Relic account access is managed outside the CRM (IT / Platform team).
- CRM roles (Onboarding, Telecaller, etc.) do **not** grant New Relic access.
- Custom events contain user email and lead IDs — treat NR dashboards with the same care as production CRM data.

---

## Limitations

- **No browser RUM** — page load timing and frontend JS errors are not captured by default.
- **Sampling** — at very high volume, New Relic may sample transactions; custom events are typically unsampled but subject to account limits.
- **Request body size** — bodies longer than ~4 KB on the transaction attribute are truncated; use logs for longer context when enabled.
- **Disabled agent** — if the Python agent is not installed or the process is not started via the instrumented entry point, no data is sent (the CRM continues to work normally).

---

## Related documentation

- [Observability — product overview](readme.md)
- [New Relic integration — technical documentation](../../technical/observability/newrelic.md)
