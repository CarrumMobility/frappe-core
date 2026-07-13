# Walk-in Form — Technical Documentation

**DocType:** `Lead walkin done`  
**Module:** Platform (`core` app)  
**Status:** Live

---

## Overview

The walk-in form is the hub onboarding workflow for recording a completed physical visit. Agents submit it via **Take Action → Mark WalkIn Done** on a `CRM Lead`.

Each submission:

1. Creates a `Lead walkin done` audit record
2. Updates lead status, source, and hub visit fields
3. Completes open `Visit Date` events
4. Optionally creates `Callback` or `Visit Date` events
5. Appears on the lead activity timeline

---

## Architecture

```mermaid
flowchart TB
    subgraph UI
        LTA[LeadTakeActionModal.vue]
        LA[Lead.vue / MobileLead.vue]
    end

    subgraph API
        GAL[get_lead_action_list]
        TLA[take_lead_actions]
        GWS[get_walkin_form_status]
        GRD[get_lead_referred_by_details]
    end

    subgraph Core Logic
        CRM[CRM Lead.mark_walk_in_done]
        LWD[Lead walkin done]
        US[util_service]
    end

    subgraph Output
        LEAD[CRM Lead fields]
        EVT[Event — Callback / Visit Date]
        ACT[Activity timeline]
    end

    LA --> LTA
    LTA --> GAL
    LTA --> GWS
    LTA --> GRD
    LTA --> TLA
    TLA --> CRM
    CRM --> LWD
    CRM --> US
    US --> EVT
    CRM --> LEAD
    LWD --> ACT
```

### Code layout

| Path | Purpose |
|---|---|
| `crm/fcrm/doctype/crm_lead/crm_lead.py` | `get_lead_action_list()`, `mark_walk_in_done()` |
| `crm/api/lead.py` | Whitelisted APIs: action list, take action, walk-in statuses |
| `crm/api/activities.py` | Timeline entries for walk-in submissions |
| `crm/api/referral.py` | Referrer details for Referral source |
| `crm/api/doc.py` | Hub Visit and Scheduled Walk-In list scoping |
| `crm/overrides/event.py` | Done/Override enrichment for Visit Date events |
| `core/platform/doctype/lead_walkin_done/` | Audit DocType |
| `core/services/util_service.py` | Visit event completion, callback/visit event creation |
| `core/constants/enums.py` | `MARK_WALK_IN_DONE`, `HubVisitStatus`, `WalkIn` |
| `frontend/src/components/Modals/LeadTakeActionModal.vue` | Walk-in form UI |
| `frontend/src/composables/useWalkinSourceSelection.js` | Source label + special source detection |
| `frontend/src/composables/useWalkinBusinessTypeOptions.js` | Hub-scoped business type options |
| `frontend/src/pages/WalkIn.vue` | Scheduled Walk-In list |
| `frontend/src/pages/HubVisit.vue` | Hub Visit list |
| `frontend/src/pages/CrmSettings/WalkInStatus.vue` | Admin: Onboarding status config |

---

## Data model

### Entity relationships

| Parent | Child / Related | Link field | Cardinality |
|---|---|---|---|
| `CRM Lead` | `Lead walkin done` | `lead` | 1:N |
| `CRM Lead` | `Lead walkin done` (latest) | `walkin_form_link` | 1:1 |
| `Lead walkin done` | `CRM Lead Status` | `lead_status_link` | N:1 |
| `CRM Lead` | `Event` | `reference_docname` | 1:N |
| `CRM Lead Source` (purpose=WalkIn) | Walk-in form source picker | — | N:1 per submission |

### `Lead walkin done`

| Field | Type | Notes |
|---|---|---|
| `lead` | Link → `CRM Lead` | Required |
| `source` | Data | Source label snapshot |
| `primary_status` | Data | Snapshot from status row |
| `secondary_status` | Data | Snapshot from status row |
| `lead_status_link` | Link → `CRM Lead Status` | FK to disposition row |
| `remarks` | Small Text | Agent comment |
| `callback_at` | Datetime | Callback or visit datetime |
| `callback_type` | Select | `Callback` / `Visit Date` |
| `telecaller` | Link → `User` | When source is telecaller |
| `business_type` | Data | When primary status is Interested |
| `created_by` | Link → `User` | Submitting agent |
| `walkin_form_filled_at` | Datetime | Defaults to `creation` in `before_save` |

### `CRM Lead` walk-in fields

| Field | Type | Notes |
|---|---|---|
| `walkin_form_filled_at` | Datetime | Last submission time |
| `walkin_form_link` | Link → `Lead walkin done` | Latest submission |
| `total_walkin_forms_filled` | Int | Counter; supports repeat visits |
| `hub_visit_status` | Select | `NOT_IN_HUB` / `IN_HUB` / `HUB_VISITED` |

### `CRM Lead Status` (walk-in config)

Filtered by `custom_role = Onboarding`. Flags used by form:

| Flag | Effect |
|---|---|
| `is_callback` | Show callback datetime picker |
| `is_visit_date_required` | Show future visit datetime picker |
| `is_remarks_required` | Comment mandatory |
| `is_lead_name_required` | Name mandatory if lead has no name |
| `custom_primary_status` | Primary disposition label |
| `lead_status` | Secondary disposition label |
| `position` | Sort order in UI |

### `CRM Lead Source`

Walk-in form source picker filters: `purpose = WalkIn`.

Special sources (matched case-insensitively by name/id):

| Source | Behavior |
|---|---|
| `referrals` | Loads referrer details from Carrum portal |
| `telecaller` | Requires telecaller agent selection |

---

## Submission flow

### 1. Action visibility (`get_lead_action_list`)

`mark_walk_in_done` is offered when user role is:

- `Administrator`, or
- `Onboarding`, or
- `Telecaller Lead`

```python
# crm_lead.py
actions.append({
    "action": "mark_walk_in_done",
    "label": "Mark WalkIn Done",
    "walkin_form_required": True,
})
```

### 2. Form load (frontend)

| API | Purpose |
|---|---|
| `crm.api.lead.get_walkin_form_status` | Onboarding status rows grouped by primary status |
| `crm.api.lead.get_lead_action_list` | Available actions for lead |
| `crm.api.referral.get_lead_referred_by_details` | Referrer info when source = referrals |
| Hub telecaller users endpoint | Telecaller dropdown when source = telecaller |

### 3. Submit (`take_lead_actions`)

```
POST crm.api.lead.take_lead_actions
{
  "lead_id": "<lead>",
  "action": "mark_walk_in_done",
  "source": "<source label>",
  "source_pk": "<crm_lead_source.name>",
  "lead_status": "<crm_lead_status.name>",
  "remarks": "<comment>",
  "callback_datetime": "<optional>",
  "scheduled_visit_date": "<optional>",
  "callback_type": "Callback" | "Visit Date",
  "telecaller": "<user or hub telecaller id>",
  "business_type": "<optional>",
  "lead_name": "<optional>",
  "hub_id": "<optional>",
  "hub_name": "<optional>"
}
```

### 4. Server processing (`mark_walk_in_done`)

```
assert_role_for_walkin()
validate status, source, remarks, name
create Lead walkin done record
if lead not Drop/Converted → update status fields
update source / source_id
mark_visit_date_events_as_completed(lead_id)
if callback_datetime → create_event_for_callback()
if scheduled_visit_date → create_event_for_visit_date()
set hub_visit_status = HUB_VISITED
set walkin_form_filled_at, walkin_form_link
increment total_walkin_forms_filled
if LEAD type and no hub_id → set hub_id, custom_hub_name
save lead
```

---

## Event integration

| Trigger | Method | Effect |
|---|---|---|
| Walk-in submitted | `mark_visit_date_events_as_completed()` | Open Visit Date events → `callback_status = Completed` |
| Callback disposition | `create_event_for_callback()` | New `Callback` event |
| Future visit disposition | `create_event_for_visit_date()` | New `Visit Date` event |
| Unscheduled walk-in | `create_event_for_walkin_completed()` | **Defined but not called** |

### Scheduled Walk-In list enrichment

`CustomEvent.parse_list_data()` adds:

| Column | Logic |
|---|---|
| **Done** | Linked lead has `hub_visit_status == HUB_VISITED` |
| **Override** | A newer Visit Date event exists for the same lead |

---

## Gate App integration

`crm.api.lead.update_lead` (Gate App webhook):

| Scenario | Behavior |
|---|---|
| New lead (by phone) | Creates lead, sets `IN_HUB`, gate ticket fields |
| Existing lead | Sets `IN_HUB`, **clears** `walkin_form_filled_at` and `walkin_form_link`, updates gate ticket |

Walk-in form submission later sets `hub_visit_status = HUB_VISITED`.

---

## Activity timeline

`crm.api.activities.append_lead_walkin_done_activities()` adds entries with:

```python
{
    "activity_type": "lead_walkin_done",
    "data": {
        "source": ...,
        "primary_status": ...,
        "secondary_status": ...,
        "remarks": ...,
        "callback_at": ...,
        "business_type": ...,
    }
}
```

Rendered in `Activities.vue` as **Walk-in Form Submitted**.

---

## Permissions

| Layer | Rule |
|---|---|
| Action visibility | `get_lead_action_list()` — Onboarding / Telecaller Lead / Administrator |
| `get_walkin_form_status` | `_assert_role_for_walkin()` — same roles |
| `mark_walk_in_done()` | Inline `assert_role_for_walkin()` — throws `PermissionError` |
| DocType `Lead walkin done` | JSON: System Manager; runtime: `role_perm_service` grants CRM agent roles |
| Saves | `ignore_permissions=True` on walk-in done and lead saves |

---

## Validation rules

| Rule | Location | Behavior |
|---|---|---|
| Role check | `mark_walk_in_done()` | Throws if not Onboarding / Telecaller Lead / Admin |
| Status required | `mark_walk_in_done()` | Throws if `lead_status` missing |
| Source required | `mark_walk_in_done()` | Throws if `source` missing |
| Remarks required | Status flag `is_remarks_required` | Throws if empty |
| Name required | Status flag `is_lead_name_required` | Throws if lead has no name |
| Invalid callback type | `mark_walk_in_done()` | Throws on type mismatch |
| Telecaller not found | `_resolve_walkin_telecaller_user()` | Throws if unresolvable |
| Referral details | Frontend | Blocks submit until portal data loads |
| Business type | Frontend | Required when primary status is Interested |

### Status update exceptions

| Lead state | Status fields updated? |
|---|---|
| Normal | Yes |
| `primary_status = Drop` | No — visit still recorded |
| `primary_status = Converted` | No — visit still recorded |

---

## API reference

| Method | Module | Auth | Description |
|---|---|---|---|
| `get_lead_action_list` | `crm.api.lead` | Whitelisted POST | Returns available actions including walk-in |
| `take_lead_actions` | `crm.api.lead` | Whitelisted POST | Executes `mark_walk_in_done` |
| `get_walkin_form_status` | `crm.api.lead` | Whitelisted | Onboarding status rows for form |
| `get_lead_referred_by_details` | `crm.api.referral` | Whitelisted | Referrer details for Referral source |
| `update_lead` | `crm.api.lead` | Whitelisted POST | Gate App — sets IN_HUB, clears walk-in pointers |

---

## Configuration

### CRM Settings — Walk-In Status

Path: **CRM Settings → Walk-In Status**

- DocType: `CRM Lead Status`
- Filter: `custom_role = Onboarding`
- Quick entry layout: `Walk-In Status Quick Entry` (`crm_fields_layout.py`)
- Defaults API: `get_lead_status_create_defaults(usage='walkin_status')`

### CRM Settings — Lead Source

Path: **CRM Settings → Lead source**

- Create sources with `purpose = WalkIn`
- Include `referrals` and `telecaller` for special flows

> Default install seeds `"Walk In"` with `purpose = Manual Selection` — not usable by walk-in form picker.

### Tab permissions

Seeded in `seed_default_crm_tab_permissions.py`:

- `Scheduled Walk-In`
- `Hub Visit`

---

## Agent performance metrics

Walk-in KPIs derived from `Event` rows with `event_category = Visit Date`:

| Metric | Source |
|---|---|
| `new_walkin_schedules` | Visit Date events created today (excl. Override) |
| `scheduled_walkin` | Visit Date events scheduled for today |
| `completed_scheduled_walkin` | Today's visits with status Completed |
| `unique_schedules_walkin` | Distinct leads with Visit Date events created today |

Computed in `agent_performance.py` and `agent_performance_dashboard.py`.

---

## Known limitations

1. `create_event_for_walkin_completed()` is implemented but **never invoked** — unscheduled walk-ins do not auto-create a completed Visit Date event
2. No failure log or retry queue (unlike Lead Sync Source)
3. Referral source depends on Carrum portal API availability
4. `test_lead_walkin_done.py` is a stub — no behavioral tests
5. Walk-in form sources must be manually configured (`purpose = WalkIn`)

---

## File reference

```
apps/core/core/platform/doctype/lead_walkin_done/
├── lead_walkin_done.json
├── lead_walkin_done.py
└── lead_walkin_done.js

apps/core/core/services/
├── util_service.py          # mark_visit_date_events_as_completed, create_event_for_*
├── role_perm_service.py     # Agent permissions on Lead walkin done
├── agent_performance.py     # Walk-in schedule metrics
└── agent_performance_dashboard.py

apps/core/core/constants/enums.py

apps/crm/crm/fcrm/doctype/crm_lead/
├── crm_lead.py              # mark_walk_in_done, get_lead_action_list
└── crm_lead.json            # walkin + hub_visit fields

apps/crm/crm/api/
├── lead.py                  # get_walkin_form_status, take_lead_actions
├── activities.py            # Timeline entries
├── referral.py              # Referrer details
└── doc.py                   # List view scoping

apps/crm/crm/overrides/event.py

apps/crm/frontend/src/
├── components/Modals/LeadTakeActionModal.vue
├── composables/useWalkinSourceSelection.js
├── composables/useWalkinBusinessTypeOptions.js
├── pages/WalkIn.vue
├── pages/HubVisit.vue
└── pages/CrmSettings/WalkInStatus.vue
```
