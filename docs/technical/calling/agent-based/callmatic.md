# Callmatic — Agent Based Dialing

**Vendor:** Callmatic  
**Calling method:** `Agent`  
**Backend:** `start_callmatic_based_manual_dial`

---

## Flow

1. Load Carrum user profile (`fetch_carrum_user_data_using_frappe_username`)
2. Resolve **DID** (caller ID):
   - User `did` on profile, **or**
   - Carrum config `DID_FOR_C2C` keyed by `defaultHub.name` (case-insensitive)
   - Missing → `{ is_valid: false, message: "DID isn't configured to you'r account connect with kapil.rohilla@carrum.co.in" }`
3. Load Callmatic campaign from Global Config `default_callmatic_outbound_campaign`
4. Create Call Session (`vendor_name=Callmatic`, `calling_method=Agent`)
5. `callmatic_client.trigger_call`:
   - `phoneNumber` = agent phone (`userContact.phoneNo`)
   - `variables.fromNumber` = DID
   - `variables.transferNumber` = lead mobile
   - `variables.callSessionId` = Call Session name
   - Callback → `core.api.call.callmatic_start_call_webhook`
6. On API failure → `FAILED` + `failure_reason`
7. On success → `INITIATED` + `agent_call_id` = Callmatic `callId`

---

## Webhook (single, end-of-call)

| Webhook | Handler |
|---|---|
| `callmatic_start_call_webhook` | `handle_callmatic_start_call_webhook_internal` |

Loads session from `variables.callSessionId`. Updates status, duration, recording, hangup/failure fields via `resolve_callmatic_hangup_reason_and_by`.

**No intermediate socket events** — UI does not get live Agent/Customer connected updates like Smartflo.

---

## Status mapping

### Agent leg (no transfree data)

| Callmatic `status` | Call Session | User message |
|---|---|---|
| `completed` | `DISCONNECTED` (with transfree) | Normal end |
| `busy` | `FAILED` | Agent line busy |
| `no-answer` | `FAILED` | Agent did not answer |
| `not-reachable` | `FAILED` | Agent phone not reachable |
| `caller-cancelled` | `FAILED` | Agent cancelled before answer |

### Customer leg (transfree present)

| Transfree `status` | Call Session |
|---|---|
| `completed` | `DISCONNECTED` |
| `busy` / `no-answer` / `not-reachable` | `OB Missed` |
| `failed` | `FAILED` |

---

## Configuration

| Config | Purpose |
|---|---|
| `role_based_default_calling_vendor` | Route Telecaller role to `Callmatic` |
| `default_callmatic_outbound_campaign` | Campaign id/name |
| `DID_FOR_C2C` | Carrum API hub → DID map |
| `callmatic_api_key` | Callmatic API auth |
| `hostname` | Webhook callback base URL |
| `carrum_base_url`, `carrum_token` | Carrum user + config API |

---

## User-visible data

- **Start:** toast success/failure only (no live popup stages)
- **After webhook:** Call Session row in Lead Activities with final status, duration, failure/hangup fields in detail modal
- **Recording:** stored on `recording_url` when Callmatic sends it (not shown in activity list by default)
