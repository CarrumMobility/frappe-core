# Calling — Technical Documentation

**Module:** `core` (`call_service`, `core.api.call`) + CRM telephony UI  
**Primary DocType:** `Call Session`  
**Vendors:** Smartflo, Callmatic

---

## Overview

CRM telephony is split into two **calling methods** (stored on every `Call Session` as `calling_method`):

| Method | User-facing name | Description |
|---|---|---|
| **Agent** | Agent based dialing | Telecaller clicks call on a **CRM Lead**; system rings the agent first, then the customer |
| **Dialer** | Dialer based dialing | Agent runs a **Smartflo dialer session**; platform auto-dials leads/callbacks from campaign |

Both methods write to the same **`Call Session`** record and share disposition, activities, and call history UI.

---

## Architecture

```mermaid
flowchart TB
    subgraph UI [CRM Frontend]
        LeadBtn[Lead call button]
        DialerUI[Dialer session UI]
        CallPopup[CustomCallUI]
    end

    subgraph API [core.api.call]
        Start[start_call]
        DialerSession[start_dialer_session]
        Webhooks[Vendor webhooks]
        Disposition[submit_disposition]
    end

    subgraph Service [call_service.py]
        AgentFlow[Agent based flows]
        DialerFlow[Dialer based flows]
    end

    subgraph Storage [(Call Session)]
    end

    LeadBtn --> Start
    DialerUI --> DialerSession
    Start --> AgentFlow
    DialerSession --> DialerFlow
    Webhooks --> AgentFlow
    Webhooks --> DialerFlow
    AgentFlow --> Storage
    DialerFlow --> Storage
    AgentFlow --> CallPopup
    DialerFlow --> CallPopup
    Disposition --> Storage
```

---

## Call Session

Every call creates (or updates) a **Call Session** linked to a **CRM Lead**.

| Field | Purpose |
|---|---|
| `calling_method` | `Agent` or `Dialer` |
| `vendor_name` | `Smartflo` or `Callmatic` |
| `direction` | `INBOUND` or `OUTBOUND` |
| `status` | Lifecycle state (see below) |
| `agent` | Frappe user who handled the call |
| `lead` / `lead_phone` | CRM Lead and dialed number |
| `agent_call_id` | Vendor call id |
| Disposition fields | Set via dispose flow |
| `failure_reason` / `hangup_*` | Error and hangup metadata |

### Status values

| Status | Meaning |
|---|---|
| `INITIATED` | Call requested; agent not yet connected |
| `AGENT_CONNECTED` | Agent answered (Smartflo Agent flow) |
| `CUSTOMER_CONNECTED` | Customer on line |
| `OB Missed` | Outbound — customer did not connect |
| `IB Missed` | Inbound — missed |
| `DISCONNECTED` | Call ended after connect |
| `DISPOSED` | Disposition saved |
| `FAILED` | Start failure, agent no-answer, or vendor error |

---

## Vendor selection

Configured via Global Config `role_based_default_calling_vendor` (JSON map of Frappe role → vendor name).

Frontend reads flags from `crm.integrations.api.is_call_integration_enabled`:

- **Smartflo:** user has Smartflo credentials + telephony integration type configured
- **Callmatic:** user's role maps to `Callmatic` in role-based vendor config

**Agent based dialing** can use either vendor depending on role.  
**Dialer based dialing** is implemented for **Smartflo** only today.

---

## API entry points

| Method | Purpose |
|---|---|
| `core.api.call.start_call` | Start **Agent based** call from Lead |
| `core.api.call.end_call` | End active Agent call (Smartflo) |
| `core.api.call.start_dialer_session` | Start dialer session |
| `core.api.call.end_dialer_session` | End dialer session |
| `core.api.call.submit_disposition` | Save disposition on Call Session |
| `core.api.call.reconcile_active_calls` | Scheduler: stale Smartflo Agent `INITIATED` → `FAILED` |

---

## Documentation layout

| Path | Contents |
|---|---|
| [agent-based/README.md](./agent-based/README.md) | Agent based dialing (generic) |
| [agent-based/smartflo.md](./agent-based/smartflo.md) | Smartflo Agent implementation |
| [agent-based/callmatic.md](./agent-based/callmatic.md) | Callmatic Agent implementation |
| [dialer-based/README.md](./dialer-based/README.md) | Dialer based dialing (generic) |
| [dialer-based/smartflo.md](./dialer-based/smartflo.md) | Smartflo dialer implementation |

**Product guides** (telecaller-facing): [../../product/calling/README.md](../../product/calling/README.md)

---

## User-visible data (shared)

### Live call — CustomCallUI

Socket events drive the floating call popup (`CustomCallUI.vue`):

- Lead ID, direction (IB/OB), lead source, DP name
- Line status and call timer when connected
- Disconnect reason and retry for failed Agent calls

### Lead → Activities → Calls

`crm.api.activities._get_linked_call_sessions_for_lead` returns Call Sessions with caller/receiver, status, duration, direction.

### Call Session detail modal

`CallSessionDetailModal.vue` shows agent, status, disposition fields, hangup/failure reason, direction, duration.

Status labels: `apps/crm/frontend/src/utils/callLog.js` → `callSessionStatusLabelMap`.

---

## Code reference

```
apps/core/core/api/call.py
apps/core/core/services/call_service.py
apps/core/core/platform/doctype/call_session/
apps/crm/frontend/src/components/Telephony/CustomCallUI.vue
apps/crm/frontend/src/socket.js
apps/crm/crm/api/activities.py
```
