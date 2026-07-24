# Agent Based Dialing — Smartflo

**Vendor:** Smartflo  
**For:** Telecallers whose role uses Smartflo for Agent based dialing

---

## What to expect

Smartflo Agent based dialing gives you **live updates** in the call popup as the call progresses:

1. **Call initiated** — CRM sent the request; your phone/softphone will ring
2. **Agent connected** — you answered
3. **Customer connected** — lead is on the line; timer starts
4. **Disconnected** or **OB Missed** — call ended

You should **answer the Smartflo softphone** (or configured extension) when CRM initiates the call.

---

## Before you call

Checklist:

- [ ] Smartflo softphone is **logged in**
- [ ] No active **dialer session**
- [ ] Lead has a valid mobile number
- [ ] You are assigned (or allowed) to call this lead

---

## During the call

The floating popup shows lead context and status. When **customer connected**, use the timer and lead link to stay oriented.

**Hang up** from your phone or CRM end-call when your process allows.

---

## If something goes wrong

| Situation | What you see | What to do |
|---|---|---|
| You don't answer within ~30 seconds | **Failed** — *Not answered by Agent in 30 seconds* | Click **Retry**; pick up faster |
| Softphone not logged in | **Failed** — *Login smartflo softphone & accept call from CRM* | Log into softphone; retry |
| Customer doesn't answer | **OB Missed** | Dispose and schedule callback if needed |
| Customer missed message in popup | *Call missed by customer* | Dispose per campaign rules |

---

## After the call

1. Complete **disposition** when prompted.
2. Verify the call on **Activities → Calls**.
3. Check **Call session** detail if you need hangup reason or remarks.

---

## Related

- [Agent based dialing (generic)](./README.md)
- [Technical — Smartflo Agent](../../technical/calling/agent-based/smartflo.md)
