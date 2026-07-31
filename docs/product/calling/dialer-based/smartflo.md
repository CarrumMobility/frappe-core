# Dialer Based Dialing — Smartflo

**Vendor:** Smartflo  
**For:** Telecallers running campaign dialer sessions

---

## Session workflow

### Start

1. Select your **campaign** (modal or dialer UI).
2. CRM logs you into Smartflo and starts the **dialer session**.
3. Session status becomes **ACTIVE** — you are in the queue.

### During session

- Smartflo dials **automatically** — do not manually dial from the lead page.
- When a call **connects**, CRM opens the **call popup** with lead info.
- **Talk**, then **hang up** when done.
- **Dispose** every call — disposition updates the lead and frees you for the next dial.

### End

1. Click **End session**.
2. Provide **inactive reason** (required).
3. Session closes — you can use **Agent based dialing** on leads again.

---

## Outbound vs inbound dialer

| Direction | What happens |
|---|---|
| **Outbound** | Platform dials the lead's number; you see **Outgoing** |
| **Inbound** | Caller reaches campaign DID; CRM may create/match lead; you see **Incoming** |

Missed inbound calls may trigger a **notification** to the assigned telecaller.

---

## Disposition

Two ways disposition can land in CRM:

1. **You dispose in CRM** after the call — recommended for full control (callbacks, visits).
2. **Smartflo sends disposition** — CRM maps vendor code to your disposition list.

If you disconnect without disposing, CRM may **auto-dispose** in some cases (toast notification).

---

## Outcomes you will see

| Status | Meaning |
|---|---|
| **Customer connected** | Call was live (initial state on connect) |
| **Disconnected** | Call ended after conversation |
| **OB Missed** | Outbound — no answer |
| **IB Missed** | Inbound — missed |
| **Disposed** | Disposition saved |

---

## Tips for agents

- Stay in **READY** state — avoid long gaps without disposing.
- Use **break** instead of leaving session open if stepping away briefly.
- Read **Failure reason** on Call session if a dial fails technically.
- Check **Activities → Calls** on the lead if you need call history for callbacks.

---

## Related

- [Dialer based dialing (generic)](./README.md)
- [Technical — Smartflo dialer](../../technical/calling/dialer-based/smartflo.md)
