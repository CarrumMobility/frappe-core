# Smartflo — Dialer Based Dialing

**Vendor:** Smartflo  
**Calling method:** `Dialer`  
**Default telephony vendor:** Smartflo (`default_telephony_vendor`)

---

## Session start

`core.api.call.start_dialer_session` → `_handle_smartflo_start_dialer_session`:

1. Smartflo campaign login (`handle_login_session_api`)
2. Start dialer session API (`handle_start_or_end_session_api`, start=true)
3. Insert `User dialer session logs` with `status=ACTIVE`
4. Set Agent Performance dialer status → `READY`

End session: logout/end API + mark session log `INACTIVE` (requires reason).

---

## Webhooks

| Webhook | Handler | When |
|---|---|---|
| `dialer_call_connected_webhook` | `dialer_call_connected` → `_dialer_call_connected_locked` | Customer/agent connected on dialer |
| `dialer_call_disconnected_webhook` | `dialer_call_disconnected` → `_handle_smartflo_dialer_call_disconnected_locked` | Call ended |
| `dialer_call_disposed_webhook` | `dialer_call_disposed_webhook` → `_handle_smartflo_dialer_call_disposed_webhook` | Smartflo disposition posted |

Match existing/new sessions by `agent_call_id` (= Smartflo `call_id`).

---

## Connect webhook (`dialer_call_connected`)

Creates Call Session if not exists:

| Field | Source |
|---|---|
| `calling_method` | `Dialer` |
| `direction` | `Dialer (outbound)` → OUTBOUND, else INBOUND |
| `status` | `CUSTOMER_CONNECTED` |
| `lead` | Find or create by customer phone |
| `agent` | Map from webhook agent email |
| `campaign_id` / `campaign_name` | Payload |
| `lead_source_during_call` | Inbound DID mapping when applicable |

Publishes `dialer_call_connected` socket → CustomCallUI.

---

## Disconnect webhook (`dialer_call_disconnected`)

Updates or creates Call Session:

| Condition | Status |
|---|---|
| `answered_agent` present | `DISCONNECTED` |
| Outbound, no agent answer | `OB Missed` |
| Inbound, no agent answer | `IB Missed` |

Also sets hangup fields, recording URL, duration, ring time.  
Inbound missed calls may notify assigned telecaller.

Publishes disconnect socket → dispose flow or disconnect notice.

---

## Disposed webhook (`dialer_call_disposed_webhook`)

Maps Smartflo disposition code → CRM Lead Status via `dialer_disposition_name`:

- Sets `DISPOSED`, disposition fields, remarks
- Updates CRM Lead
- Creates callback / visit events when configured
- Publishes `call_auto_disposed` when applicable

---

## Disposition (CRM-side)

`submit_disposition` with `calling_method: Dialer`:

- Updates Call Session → `DISPOSED`
- Syncs disposition to Smartflo API when configured
- Updates lead, callbacks, visit dates
- Sets Agent Performance → `READY`

---

## Status summary

| Phase | Typical status |
|---|---|
| Connected | `CUSTOMER_CONNECTED` |
| Ended (answered) | `DISCONNECTED` |
| Outbound miss | `OB Missed` |
| Inbound miss | `IB Missed` |
| Disposed | `DISPOSED` |

---

## Realtime events

| Event | UI |
|---|---|
| `dialer_call_connected` | Show connected call popup |
| Disconnect payloads | Dispose modal or missed notice |
| `call_auto_disposed` | Toast for auto-disposition |

---

## Configuration

- Smartflo credentials + campaign on Carrum user
- CRM Lead Status rows with `dialer_disposition_name` for vendor code mapping
- Inbound lead source DID mapping (optional source update on connect)

---

## Code reference

```
call_service.start_dialer_session / end_dialer_session
call_service.dialer_call_connected
call_service.dialer_call_disconnected
call_service.dialer_call_disposed_webhook
call_service._handle_dialer_submit_disposition
core.api.call (webhook endpoints)
```
