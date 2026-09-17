# Scheduled jobs (ERP)

**Product / production guide:** [../product/crons.md](../product/crons.md)

Source of truth: `scheduler_events` in each app’s `hooks.py`.

Frappe interval keys map roughly as:


| Key                      | Typical cadence                                                            |
| ------------------------ | -------------------------------------------------------------------------- |
| `all`                    | Every scheduler tick (often ~4 minutes; see site/bench scheduler settings) |
| `hourly` / `hourly_long` | Hourly                                                                     |
| `daily` / `daily_long`   | Daily                                                                      |
| `weekly`                 | Weekly                                                                     |
| `monthly_long`           | Monthly                                                                    |
| `cron`                   | Explicit crontab expression (site timezone / UTC depends on bench config)  |


---



## Core (`/core/hooks.py`)



### Active


| Schedule       | Method                                                                                          | Purpose                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `all`          | `core.services.call_service.reconcile_active_calls`                                             | Reconcile active/stale Smartflo call sessions (e.g. mark long-`INITIATED` calls as failed).                                   |
| `*/30 * * * *` | `core.services.agent_performance.cron_task_update_today_telecaller_agents_performance_5_minute` | Refresh today’s Agent Performance rows for telecallers. (Hook path name says “5_minute”; expression is every **30** minutes.) |


Empty slots (no jobs): `hourly`, `daily`, `weekly`, `daily_long`, `hourly_long`, `monthly_long`.

---



## CRM (`apps/crm/crm/hooks.py`)



### Active


| Schedule       | Method                                                                                         | Purpose                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `all`          | `crm.api.event.trigger_offset_event_notifications`                                             | Event notifications for minute/hour offset intervals.                                                         |
| `hourly`       | `crm.api.event.trigger_hourly_event_notifications`                                             | Hourly-interval event notifications.                                                                          |
| `daily`        | `crm.module_maintenance.doctype.maintenance_ticket.scheduled_tasks.promote_followup_scheduled` | Move Maintenance Tickets from **Followup Scheduled** → **Followup Pending** when `last_followup_date` is due. |
| `daily_long`   | `crm.lead_syncing.background_sync.sync_leads_from_sources_daily`                               | Background lead sync for sources with frequency **Daily**.                                                    |
| `hourly_long`  | `crm.lead_syncing.background_sync.sync_leads_from_sources_hourly`                              | Background lead sync for sources with frequency **Hourly**.                                                   |
| `monthly_long` | `crm.lead_syncing.background_sync.sync_leads_from_sources_monthly`                             | Background lead sync for sources with frequency **Monthly**.                                                  |
| `*/10 * * * *` | `crm.lead_syncing.background_sync.sync_leads_from_sources_10_minutes`                          | Lead sync for sources with frequency **Every 10 Minutes**.                                                    |
| `*/15 * * * *` | `crm.lead_syncing.background_sync.sync_leads_from_sources_15_minutes`                          | Lead sync for sources with frequency **Every 15 Minutes**.                                                    |
| `*/5 * * * *`  | `crm.scheduler.check_due_callback_events`                                                      | Trigger due Callback / Visit Date events that are still **Scheduled**.                                        |
| `0 23 * * *`   | `crm.api.event.mark_today_events_as_missed`                                                    | End of day: mark today’s unfinished Callback / Visit Date events as **Missed**.                               |