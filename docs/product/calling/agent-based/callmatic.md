# Agent Based Dialing — Callmatic

**Vendor:** Callmatic  
**For:** Telecallers whose role uses Callmatic for Agent based dialing

---

## What to expect

Callmatic Agent based dialing works differently from Smartflo:

1. You click **Call** on the lead
2. You see **“Call initiated”** if the request succeeded
3. **Callmatic rings your mobile** (from your Carrum profile)
4. After you answer, the customer is connected through Callmatic
5. When the call **fully ends**, CRM receives the outcome and updates the lead timeline

There are **no live “agent connected / customer connected” steps** in the popup — the final result appears after the call completes.

---

## Before you call

Checklist:

- [ ] Your **mobile number** on Carrum profile is correct (`userContact.phoneNo`)
- [ ] A **caller ID (DID)** is configured for you or your default hub
- [ ] No active **dialer session**
- [ ] Lead has a valid mobile number

If DID is missing, you will see:

> *DID isn't configured to you'r account connect with kapil.rohilla@carrum.co.in*

Contact your administrator to configure **DID_FOR_C2C** for your hub.

---

## During the call

- Answer your **mobile** when Callmatic rings
- You may not see a multi-stage popup — that is normal for Callmatic
- Complete the conversation as usual

---

## After the call — outcomes

CRM updates the Call Session when Callmatic sends the result:

| Outcome | Status you may see | Meaning |
|---|---|---|
| Normal conversation | **Disconnected** | Call completed |
| You didn't answer | **Failed** | *Agent did not answer* |
| Your line busy | **Failed** | *Agent line was busy* |
| Phone unreachable | **Failed** | *Agent's phone number could not be reached* |
| You cancelled before answer | **Failed** | *Agent cancelled call before it was answered* |
| Customer didn't answer | **OB Missed** | Customer-side no answer |

Open **Call session** detail for **Failure reason** or **Hangup reason**.

---

## Tips

- Keep your profile phone number up to date — Callmatic always calls that number first.
- If calls fail repeatedly, ask admin to verify **DID** and **Callmatic campaign** configuration.
- Always **dispose** after connected calls so lead status stays correct.

---

## Related

- [Agent based dialing (generic)](./README.md)
- [Technical — Callmatic Agent](../../technical/calling/agent-based/callmatic.md)
