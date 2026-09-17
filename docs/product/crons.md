# Scheduled jobs (ERP)

---

## What this controls

Frappe’s **scheduler** runs jobs on a fixed cadence. If the scheduler or background workers are off, these automations stop even though Desk still works for interactive users.


| Area                    | What users see when jobs run                                     | What breaks if jobs stop                              |
| ----------------------- | ---------------------------------------------------------------- | ----------------------------------------------------- |
| Calling                 | Stale “initiated” Smartflo calls get cleaned up                  | Sessions can sit in `INITIATED` indefinitely          |
| Agent performance       | Today’s telecaller metrics refresh on a schedule                 | Dashboards/performance rows go stale                  |
| Callbacks / visit dates | Due events fire; unfinished today events become Missed overnight | Callbacks stay Scheduled; Missed status never applied |
| Event reminders         | Offset / hourly / daily / weekly notifications fire              | Reminder notifications stop                           |
| Lead sync               | Facebook / OLX (etc.) sources pull on their configured frequency | New external leads stop arriving until manual sync    |
| Maintenance follow-up   | Scheduled follow-ups move to Followup Pending on the due date    | Tickets stay in Followup Scheduled past the date      |


---

## Job catalog (business view)

### Core


| Cadence                   | Outcome                                                                |
| ------------------------- | ---------------------------------------------------------------------- |
| Every few minutes (`all`) | Reconcile active Smartflo calls; mark stale initiated sessions failed. |
| Every 30 minutes          | Refresh **today’s** Agent Performance data for telecallers.            |




### CRM — events & callbacks


| Cadence                   | Outcome                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| Every few minutes (`all`) | Fire event notifications based on minute/hour offsets.                   |
| Hourly                    | Hourly-interval event notifications.                                     |
| Daily                     | Daily-interval event notifications.                                      |
| Weekly                    | Weekly-interval event notifications.                                     |
| Every 5 minutes           | Trigger due **Callback** / **Visit Date** events still in **Scheduled**. |
| Every day at 23:00        | Mark today’s unfinished Callback / Visit Date events as **Missed**.      |


### CRM — lead sync

Lead Sync Sources only sync when **Enabled** and their **Background sync frequency** matches a scheduled job:


| Source frequency setting | Scheduler cadence                                                             |
| ------------------------ | ----------------------------------------------------------------------------- |
| Every 5 Minutes          | Intended `*/5` (see technical note: may conflict with callback cron in hooks) |
| Every 10 Minutes         | Every 10 minutes                                                              |
| Every 15 Minutes         | Every 15 minutes                                                              |
| Hourly                   | `hourly_long`                                                                 |
| Daily                    | `daily_long`                                                                  |
| Monthly                  | `monthly_long`                                                                |


Operators can still use **Sync now** / force sync from Desk when schedule sync is not enough.

### CRM — maintenance


| Cadence | Outcome                                                                                                                                |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Daily   | Maintenance tickets with **Followup Scheduled** and due `last_followup_date` move to **Followup Pending** (appear in follow-up lists). |


---

## Operator actions when something looks stuck

1. Check System Settings → Enable Scheduler.
2. Check that scheduler/worker processes are up on the server.

