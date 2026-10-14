# Bill Approval Engine — Backend Code Walkthrough

> **Scope:** Function-by-function reference for the backend code that computes bill/ticket approval state. This is the "how does the code actually work" companion to [`bill_approval_flows.md`](../../../crm/docs/bill_approval_flows.md) (the "what happens when the FE clicks Approve" product flow) and [`MAINTENANCE_MODULE.md`](../../../crm/docs/MAINTENANCE_MODULE.md) sections 16–27/40 (the full business rules). Read those first for the *why this feature exists*; this doc is for *why this specific function is written this way*.
>
> **Companion doc:** [`bill_approval_engine_frontend.md`](./bill_approval_engine_frontend.md) — the JS mirror of this same engine.
> **Product-facing doc:** [`../product/bill_approval_engine.md`](../product/bill_approval_engine.md) — what all of this looks like on screen.
> Relocated 2026-09-29 from `apps/crm/docs/` to the `apps/core/docs/technical` convention.

---

## Recent fixes (2026-09-29)

Real bugs were found and fixed across two rounds this session — the first while investigating a zero-amount Tax Invoice bill that got stuck showing "Pending"; the second, later the same day, while investigating ticket MNT-32634 landing on `"Closed"` when it should have been `"Finance Approved"`, and a Finance approval that visibly needed two clicks to "take." **If you read an older copy of this doc (or `MAINTENANCE_MODULE.md`) describing the behavior below as intentional, that description is wrong — it was describing a bug.**

**Round 1:**

1. **Workflow-transition rollback (§6).** `close_zero_amount_tax_invoice_bill` closing the ticket via `ticket.save()` was silently rejected by Frappe's built-in Workflow transition check (the "Fleet Maintenance Approval New" workflow has no edge from e.g. `"FE Pending (TI)"` straight to `"Closed"`), which rolled back the **entire request** — including the bill's own `"Closed"` write made moments earlier in the same request. Fixed by setting `ticket.flags.ignore_workflow_transition = True` before that specific save, and by making `MaintenanceTicket.validate_workflow()` (in `maintenance_ticket.py`) respect that flag.
2. **`finance_approval_status` leaking onto a closed zero-amount bill (§6, §9).** When a *sibling* Tax Invoice bill pushes the ticket into `"Finance Pending"`/`"Finance Approved"`, `Maintenance Ticket.on_update` → `_sync_finance_approval_to_bills_if_needed` → `sync_finance_approval_to_linked_bills` (`finance_approval_sync.py`) used to stamp `finance_approval_status` onto **every** Tax Invoice bill on the ticket, with no regard for whether that bill was individually `"Closed"`. If the zero-amount bill hadn't been approved (closed) *yet* at the moment that stamp happened, it got `finance_approval_status = "Pending"` and nothing ever cleared it afterward — so it kept showing up on the Finance dashboard. Fixed two ways: `sync_finance_approval_to_linked_bills` now skips any bill whose resolved status is `"Closed"`, **and** `close_zero_amount_tax_invoice_bill` now explicitly sets `finance_approval_status = None` at the moment it closes the bill (this is the one that actually matters for timing — it clears a stamp that already happened, not just prevents future ones).
3. **`recalculate_bill_approval_statuses` (`crm/api/maintenance_api.py`) threw on every page load.** It called `sync_maintenance_ticket_workflow_from_bills(maintenance_ticket)` with only one argument; the function requires the triggering bill `doc` too. Every Pre Invoice section mount hit a 500 (silently swallowed by the frontend's try/catch) and the recalculation never actually ran. Fixed by passing the last-processed bill doc through.

The frontend also had two bugs of its own that made these backend fixes invisible until they were fixed too — see the "Recent fixes" section of [`bill_approval_engine_frontend.md`](./bill_approval_engine_frontend.md).

**Round 2** (§4, §6 — supersedes part of round 1's fix #2):

4. **`get_target_ticket_workflow_from_tax_invoice_bills` used `any(status == "Closed" ...)`, not `all(...)`.** Round 1 fixed this function so a fully-cleared Tax Invoice chain containing a `"Closed"` bill returned `"Closed"` instead of unconditionally `"Finance Approved"` — but it used `any()`, so a ticket with **one** zero-amount `"Closed"` bill and **one** genuinely `"Finance Approved"` bill also came out `"Closed"`, hiding the real finance sign-off (reported against ticket MNT-32634). Changed to `all()`: the ticket is `"Closed"` only when *every* Tax Invoice bill got there via the zero-amount shortcut; a mix returns `"Finance Approved"`. The frontend's `getTargetTicketWorkflowState` and `getDisplayTicketWorkflowStateForTicket` got the matching `every()` fix (see the frontend doc).
5. **`close_zero_amount_tax_invoice_bill`'s Case 2 no longer closes the ticket.** It used to close the ticket itself whenever every *other* Tax Invoice bill was already `"Finance Approved"` — the same bug as #4, just written directly into this function instead of the generic computation. Case 2 now only closes the *bill*; the ticket is left to the generic sync (§4), which (after fix #4) correctly computes `"Finance Approved"` for a mixed ticket.
6. **`sync_maintenance_ticket_workflow_from_bills` had an `if doc.bill_status == "Closed": return False` guard that silently no-op'd the whole ticket sync** whenever the triggering bill happened to already be `"Closed"` — which is exactly the case when a zero-amount bill is the *last* Tax Invoice bill on a ticket to close (e.g. its non-zero sibling already reached `"Finance Approved"` earlier). This caused the two-click Finance-approval symptom: clicking Finance's Approve button ran `finance_approve_bill`, which correctly sets `bill.finance_approval_status = "Approved"` on the in-memory doc, but between fix #4 not existing yet and this guard blocking the ticket sync in various orderings, the ticket could get stuck out of sync until a second, differently-timed save happened to run the sync uninterrupted. Removed the guard entirely — the caller (`on_maintenance_bill_after_save`) already skips this function when `close_zero_amount_tax_invoice_bill` itself closed the ticket in the same request, which is the only case that actually needs guarding.

---

## Table of Contents

1. [Core files](#1-core-files)
2. [The two-places-for-one-status problem](#2-the-two-places-for-one-status-problem)
3. [Gate indices — how a status becomes a number](#3-gate-indices--how-a-status-becomes-a-number)
4. [Ticket target computation](#4-ticket-target-computation)
5. [The re-entrancy depth guard](#5-the-re-entrancy-depth-guard)
6. [The zero-amount Tax Invoice closure rule](#6-the-zero-amount-tax-invoice-closure-rule)
7. [Auto-approval brackets (Pre Invoice)](#7-auto-approval-brackets-pre-invoice)
8. [Frappe Workflow vs this engine](#8-frappe-workflow-vs-this-engine)
9. [Adjacent files (one paragraph each)](#9-adjacent-files-one-paragraph-each)

---

## 1. Core files

| File | Responsibility |
|---|---|
| `module_maintenance/bill_approval_sync.py` | The engine: status resolution, gate-index math, ticket-state sync, auto-approval brackets, zero-amount closure, re-entrancy guard |
| `module_maintenance/tax_invoice_adherence.py` | Blocks an FE "Approve" on a Tax Invoice whose amount is outside ~80–105% of the Admin Approved Pre Invoice total |
| `module_maintenance/finance_approval_sync.py` | Pushes `finance_approval_status` onto linked bills once the ticket enters a finance-relevant state — now skips bills that are individually `"Closed"` (see Recent fixes above) |
| `module_maintenance/doctype/maintenance_ticket/maintenance_ticket.py` | Maintenance Ticket controller — `validate_workflow()` override now also skips Frappe's Workflow-transition check when `flags.ignore_workflow_transition` is set (see Recent fixes above) |
| `module_maintenance/doctype/maintenance_bill/maintenance_bill.py` | Maintenance Bill controller (`validate`/`before_save`/`before_insert`) — housekeeping only, no approval-chain logic |
| `module_maintenance/bill_approval_config.py` | Amount-bracket thresholds read by the auto-approval logic |
| `module_maintenance/pms_cycle_reset.py` | Fires the external PMS cycle-reset call when a bill/ticket first enters the approved chain |
| `crm/api/workflow.py` | `execute_workflow_action` — the *real* Frappe Workflow driver the frontend calls directly |
| `crm/api/maintenance_bill_helpers.py` | Assignment routing (`_route_bill_approval_assignment_impl`), commercial reconcile approve |
| `crm/api/maintenance_api.py` | `update_maintenance_ticket`, `finance_approve_bill`, `recalculate_bill_approval_statuses` |

---

## 2. The two-places-for-one-status problem

A Maintenance Bill's status can live in **two places at once**:

1. the `bill_status` column, and
2. a `bill_status` key nested inside the `vendor_parser_data` JSON blob — the Review Modal frontend frequently rewrites the *entire* JSON blob on every save/approve, including its own copy of the status.

These disagree more often than you'd expect — e.g. a backend routine sets the column to `"Closed"` via a bare `frappe.db.set_value` without touching the JSON, or the frontend posts a stale JSON blob alongside a fresh column value.

**`resolve_bill_status_from_row(row)`** is the single source of truth for "what is this bill's real status right now":

```python
_PERSISTABLE_BILL_STATUSES = {"Pending", "Approved", "Rejected", "FE Approved", ..., "Finance Approved", ...}
# deliberately EXCLUDES "Closed" and "Ops Pending"
```

Resolution order:
1. If **both** column and JSON are persistable and they **differ**, JSON wins (assumed to be the more recent frontend edit).
2. Otherwise, whichever of column/JSON **is** persistable wins.
3. If neither is persistable, fall back to column, then JSON, then `""`.

**Worked example:**
```
column bill_status              = "Closed"        (NOT persistable)
vendor_parser_data.bill_status  = "FE Approved"    (persistable)

resolve_bill_status_from_row(row) -> "FE Approved"
```
Rule 1 doesn't apply (only one side is persistable), so rule 2 picks the persistable one — `"FE Approved"`, **not** `"Closed"`. This is exactly why any code that force-closes a bill (see §6) must write `"Closed"` into **both** the column and the JSON — otherwise every caller of this resolver keeps reporting the bill as still open, and the ticket-sync computation (§4) will keep trying to advance it through the normal chain.

**Important — rule 3's fallback is load-bearing, don't "simplify" it away.** `"Closed"` is not persistable, so when *both* column and JSON agree on `"Closed"` (the normal case once a bill is fully closed), neither rule 1 nor rule 2 fires — the function relies on rule 3's `shell or json_st or ""` to still return `"Closed"` rather than silently falling back to some default. The frontend had exactly this bug (see [`bill_approval_engine_frontend.md`](./bill_approval_engine_frontend.md)'s Recent fixes): its equivalent function's fallback was a hardcoded `'Pending'` instead of `shellSt || jsonSt || 'Pending'`, so it turned every fully-closed bill back into `"Pending"` on screen.

The frontend mirror of this function is `resolveBillStatusFromMaintenanceRow` in `billWorkflowSync.js` — see `bill_approval_engine_frontend.md` for that side.

---

## 3. Gate indices — how a status becomes a number

**`get_bill_next_gate_index(bill_status, tax_invoice=False)`** turns one bill's status string into "how many approval gates has it cleared":

- Pre Invoice chain: 5 gates — FE, MM, FGM, SGM, Admin (`MAINTENANCE_GATE_PENDING_STATES`)
- Tax Invoice chain: 2 gates — FE, Finance (`TAX_INVOICE_GATE_PENDING_STATES`)

Return value is a **count**, not a status name: `0` = "still at the first gate", `N` (chain length) = "cleared every gate".

```
get_bill_next_gate_index("MM Approved")                        -> 2   (FE, MM cleared; FGM next)
get_bill_next_gate_index("Finance Approved", tax_invoice=True)  -> 2   (both TI gates cleared)
get_bill_next_gate_index("Closed", tax_invoice=True)            -> 2   (see quirk below)
get_bill_next_gate_index("MM Rejected")                         -> 0   (any rejection resets to the start)
```

**Load-bearing quirk:** `"Closed"` is mapped to the *same* index as `"Finance Approved"` — both mean "fully cleared" (Tax Invoice only; this function has no equivalent special case for a Pre Invoice bill literally named `"Closed"`, which shouldn't happen in practice). This lets a Tax Invoice bill that was closed for an unrelated reason (inhouse workshop, or the zero-amount rule in §6) still count as "done" when the ticket-level target is computed. The flip side: the ticket-target computation genuinely **cannot tell** "Closed because zero-value" apart from "Closed because inhouse" apart from "genuinely Finance Approved" — they all produce the same gate index. Any code path that wants the ticket to land specifically on `"Closed"` (not the generic `"Finance Approved"`) must apply its own override on top of this function's output — see `get_target_ticket_workflow_from_tax_invoice_bills` in §4, and the frontend's identically-shaped fix in `getTargetTicketWorkflowState` / `getDisplayTicketWorkflowStateForTicket`.

This function mirrors the frontend's `getBillNextGateIndex` in `billWorkflowSync.js` — see `bill_approval_engine_frontend.md`. **The two sides used to disagree on this exact quirk** (the JS version treated `"Closed"` as gate index `0`, not `chain.length` — see that doc's Recent fixes) — always re-check both sides agree before relying on this table.

---

## 4. Ticket target computation

Three functions build on each other:

```
get_target_ticket_workflow_from_maintenance_bills(bills)   # Pre Invoice bills only
get_target_ticket_workflow_from_tax_invoice_bills(bills)   # Tax Invoice bills only
compute_target_ticket_workflow_state(ticket_name)          # combines both, in order
```

Both "from_*_bills" functions use the same base rule: **take the MINIMUM gate index across all bills of that type.** The ticket sits at the gate of whichever bill is furthest behind — other bills that are further ahead just wait. Once every bill's index is at the chain's max, the function would normally return the "chain complete" state (`"FE Pending (TI)"` for Pre Invoice, `"Finance Approved"` for Tax Invoice) — **except** `get_target_ticket_workflow_from_tax_invoice_bills` has one override on top of that: if **every** one of the fully-cleared Tax Invoice bills is literally `"Closed"` (not `"Finance Approved"`), it returns `"Closed"` instead of `"Finance Approved"`. This is `all()`, not `any()` — a ticket with a mix of a zero-amount `"Closed"` bill and a genuinely `"Finance Approved"` sibling must stay `"Finance Approved"` (see Recent fixes #4 — an earlier version of this override used `any()` and got this exact mixed case wrong, reported against ticket MNT-32634).

```python
def get_target_ticket_workflow_from_tax_invoice_bills(bills):
    if not bills:
        return None
    if any(_is_rejected_status(b["bill_status"]) for b in bills):
        return "FE Pending"

    indices = [get_bill_next_gate_index(b["bill_status"], tax_invoice=True) for b in bills]
    min_idx = min(indices)
    if min_idx >= len(TAX_INVOICE_GATE_PENDING_STATES):
        if all(b["bill_status"] == "Closed" for b in bills):
            return "Closed"          # <- the override; all(), not any() — see Recent fixes #4
        return TICKET_STATE_AFTER_TAX_INVOICE_CHAIN   # "Finance Approved"
    return TAX_INVOICE_GATE_PENDING_STATES[min_idx]
```

`compute_target_ticket_workflow_state` ties them together:
1. Fetch all bills for the ticket, resolve each one's status via `resolve_bill_status_from_row`.
2. Any bill rejected anywhere → ticket target is `"FE Pending"` (send everything back).
3. No Pre Invoice bills at all → returns `None` (nothing to compute).
4. Compute the Pre Invoice target. If it's not yet `"FE Pending (TI)"` (chain not done), return that directly — Tax Invoice bills aren't even looked at yet.
5. Otherwise, hand off to the Tax Invoice computation above.

**`sync_maintenance_ticket_workflow_from_bills(ticket_name, doc)`** is the function that actually *writes* the computed target to the ticket. `doc` is the Maintenance Bill whose save just triggered this (passed through from the `on_update` hook, or from `recalculate_bill_approval_statuses` — see Recent fixes item 3 for why that argument is not optional):

```python
def sync_maintenance_ticket_workflow_from_bills(ticket_name, doc):
    if not ticket_name or not doc:
        return False

    target = compute_target_ticket_workflow_state(ticket_name)
    if not target:
        return False
    if target in ("Finance Pending", "Finance Approved") and _is_inhouse_workshop(ticket_name):
        target = "Closed"   # inhouse override

    # ... write target via frappe.db.set_value, unassign agent if terminal,
    # push finance_approval_status via finance_approval_sync.py, route assignment ...
```

**Callout — this function used to also have `if doc.bill_status == "Closed": return False` right after the null checks (removed, see Recent fixes #6).** That checked the bill that *triggered* the call, not the ticket — and a closed zero-amount bill is a completely normal, common trigger for this function (e.g. it's the *last* of several Tax Invoice bills to close, after its non-zero sibling already reached `"Finance Approved"`). With the guard in place, that call would silently no-op the entire ticket sync, which is exactly the mechanism behind the "Finance approval needs two clicks" symptom reported this session — a differently-timed second save would eventually run the sync unguarded and the ticket would catch up, making the first click look like it "didn't work." The only case that actually needs guarding — don't run the generic sync when `close_zero_amount_tax_invoice_bill` already decided and wrote the ticket's state in the same request — is handled one level up, in `on_maintenance_bill_after_save`'s `not zero_amount_ticket_closed` check, which only skips this function when it's genuinely redundant.

---

## 5. The re-entrancy depth guard

`on_maintenance_bill_after_save` is registered as Maintenance Bill's `on_update` hook, which Frappe fires on **every** save — including saves the engine performs on *itself* from inside that very hook (`close_zero_amount_tax_invoice_bill` calls `bill_doc.save()` again while already running inside the hook). Without a guard, that inner save would re-trigger the same hook recursively, re-running side effects (Pazy email, PMS reset, ticket sync) an extra time per level of nesting.

`_approval_sync_depth()` reads `frappe.flags.bill_approval_sync_depth` — a **per-request**, not per-document, counter. `on_maintenance_bill_after_save` increments it on entry and restores it in a `finally` on exit. Most side-effect blocks are gated `if depth == 0` (the outermost/original save); the generic ticket-sync call is gated `if depth <= 1 and not zero_amount_ticket_closed`.

**Trace of a normal save** (FE approves a non-zero Pre Invoice bill, `"Pending"` → `"FE Approved"`):

```
depth 0 -> bumped to 1
  entered_approved computed (depth==0)
  apply_maintenance_bill_approval_rules(doc)        # depth==0
  close_zero_amount_tax_invoice_bill(doc)            # depth==0, returns False (not Tax Invoice)
  sync_maintenance_ticket_workflow_from_bills(...)   # depth<=1, not skipped
  PMS reset (if entered_approved)
finally: depth restored to 0
```
Every side effect ran exactly once.

**Trace of the re-entrant case** (FE approves a zero-amount Tax Invoice bill):

```
depth 0 -> bumped to 1
  close_zero_amount_tax_invoice_bill(doc) matches:
    outer_depth = 1
    frappe.flags.bill_approval_sync_depth = 1 + 2 = 3      <- +2, not +1 (see below)
    bill_doc.save(...)   <- re-fires on_maintenance_bill_after_save, NESTED
      nested call: depth reads 3, bumped to 4
      every `if depth == 0` block skipped
      ticket-sync check `if depth <= 1` -> 4 is not <= 1 -> skipped
      finally: depth restored to 3
    finally (back in close_zero_amount_tax_invoice_bill): depth restored to 1
    [Case 1, or Case 2 where every sibling is Finance Approved: ticket.save() too — see §6]
  zero_amount_ticket_closed = <bool the function returned>
  depth<=1 is True BUT zero_amount_ticket_closed is True -> generic sync SKIPPED
    (it would otherwise recompute a target unaware of the "Closed" override
     just written, and — before the §4 override existed — would have stomped
     it with "Finance Approved")
finally: depth restored to 0
```

**Why +2 and not +1:** a nested call landing on depth `1` would still satisfy the ticket-sync's `depth <= 1` guard and run a redundant sync from *inside* the nested save — before the outer call has even applied its own `"Closed"` override. Bumping to depth `2` (giving the nested call depth `3`, well past `1`) fully suppresses it.

---

## 6. The zero-amount Tax Invoice closure rule

**Business rule:** when an FE clicks "Approve" on a Tax Invoice bill whose resolved net amount is exactly zero, the bill should close (`"Closed"`) instead of proceeding into `"Finance Pending"`/`"Finance Approved"` — a nil-value invoice never needs Finance's sign-off, and its `finance_approval_status` must stay `None` (never `"Pending"` or `"Approved"`) so it never shows up on the Finance dashboard.

- **Case 1** — it's the only Tax Invoice bill on the ticket → the ticket also closes.
- **Case 2** — other Tax Invoice bills exist → only this bill closes; the ticket is always left to the normal gate computation (§4), which correctly returns `"Finance Approved"` once the non-zero sibling(s) clear Finance, or `"Closed"` if every sibling also turns out to be a zero-amount `"Closed"` bill.

  **This function used to also close the ticket in Case 2** whenever every other Tax Invoice bill was already `"Finance Approved"` — removed (see Recent fixes #5), because that hid a real finance sign-off behind `"Closed"` (reported against ticket MNT-32634: one `"Closed"` zero-amount bill + one `"Finance Approved"` ₹315 bill should leave the ticket `"Finance Approved"`, not `"Closed"`).

This all lives in one function, **`close_zero_amount_tax_invoice_bill(bill_doc)`**, called from `on_maintenance_bill_after_save` at `depth == 0`, **before** the generic sync:

```python
before = bill_doc.get_doc_before_save()
old_status = resolve_bill_status_from_row(before) if before else ""
new_status = resolve_bill_status_from_row(bill_doc)
if not (old_status and new_status) or not (old_status == "Pending" and new_status == "FE Approved"):
    return False
```

This must **not** fire on an ordinary "Save changes" — editing fields (including the amount) and saving does not by itself move `bill_status` to `"FE Approved"`; only clicking Approve does. (Note this gate is stricter than the frontend doc's older description implied: it requires the transition to be specifically `"Pending"` → `"FE Approved"`, not merely "anything other than FE Approved" → `"FE Approved"`.)

Then, after confirming the resolved net amount is `~0`:

```python
sibling_bills = <every other Tax Invoice bill on the same ticket>
is_only_one_zero_tax_invoice_bill = not sibling_bills   # Case 1 — the only case that closes the ticket here
should_close_ticket_in_this_case = is_only_one_zero_tax_invoice_bill
```

**Part 1 — always runs:** close the bill itself.

```python
bill_doc.bill_status = "Closed"
_set_json_bill_status_field(bill_doc, "Closed")     # §2 — keep column and JSON in sync
bill_doc.finance_approval_status = None             # added 2026-09-29 — see Recent fixes item 2
bill_doc.save(ignore_permissions=True, ignore_version=False)
```

`bill_doc.save(...)` (not `frappe.db.set_value`, unlike almost everything else in this file) is deliberate — it lands in `tabVersion` (audit trail). It's also what makes the re-entrancy guard in §5 necessary.

**Part 2 — only when `should_close_ticket_in_this_case`:** close the ticket too.

```python
ticket = frappe.get_doc("Maintenance Ticket", ticket_name)
ticket.bill_status = "Closed"
ticket.ticket_agent_id = None
ticket.ticket_agent_name = None
ticket.followup_status = None
ticket.flags.ignore_workflow_transition = True      # added 2026-09-29 — see Recent fixes item 1
ticket.save(ignore_permissions=True, ignore_version=False)
```

The `ignore_workflow_transition` flag is required because the ticket's `bill_status` field is also the state field for the real Frappe Workflow ("Fleet Maintenance Approval New," see §8) — jumping straight from e.g. `"FE Pending (TI)"` to `"Closed"` is not a transition that workflow defines, and without the flag Frappe's `validate_workflow` would reject the save with `WorkflowPermissionError`. Because this happens inside `ticket.save()`, that exception rolls back the **whole HTTP request** — including Part 1's bill closure a moment earlier in the same request. Before this flag existed, that's exactly what made the rule look like it silently "did nothing": both writes landed back at their pre-approval values once the request rolled back, with no error surfaced to the FE (Frappe logs the exception, but the frontend's own generic error toast doesn't distinguish it from "gate not yet cleared").

The function returns `should_close_ticket_in_this_case` (Case 1 only, as of Recent fixes #5). The caller (`on_maintenance_bill_after_save`) uses that to decide whether to run the generic ticket-workflow sync afterward (§4/§5) — it must not, in Case 1, because that would be redundant (Case 1 has no other Tax Invoice bills for the generic computation to even weigh). In Case 2 the generic sync always runs and is now trusted to compute the right answer (§4's `all()` fix).

**Test coverage:** `crm/tests/test_zero_amount_tax_invoice_closure.py` covers both cases, non-zero/Pre-Invoice exclusion, idempotency, and the tabVersion audit trail. As of 2026-09-29 it should also cover: the ticket-workflow-transition bypass (Part 2 succeeding from a non-adjacent ticket state), and `finance_approval_status` ending up `None` even when a sibling bill's approval already stamped it `"Pending"` first.

---

## 7. Auto-approval brackets (Pre Invoice)

Separate concern from the zero-amount rule — this only applies to Pre Invoice bills, and skips gates based on amount rather than closing anything.

- `apply_auto_approval_for_bracket(bill_status, net_amount)` — the "plain recheck" path: if the amount fits under the *current* gate's threshold (from `bill_approval_config.get_bracket_threshold`), skip straight to `"Admin Approved"`. Used when a bill is edited without a genuine forward transition (e.g. FE edits the amount on a still-`"Pending"` bill).
- `compute_maintenance_bill_status(old_status, new_status, net_amount)` — handles the "senior lagging" multi-step jump case (one or more approvers skipped in a single save) by capping to a single chain step via `normalize_one_step_approval`, then rechecking the bracket.
- `_cumulative_pre_invoice_total(doc)` — uses the running total of this bill plus every *other* Admin Approved Pre Invoice bill on the ticket, not just this bill's own amount — closes the "split one large bill into several smaller ones to dodge escalation" loophole.

See `MAINTENANCE_MODULE.md` §16 for the default thresholds table.

---

## 8. Frappe Workflow vs this engine

**Important, easy to get wrong:** the Frappe Workflow named `"Fleet Maintenance Approval New"` attached to Maintenance Ticket has `workflow_state_field = "bill_status"` — this is the field every `frappe.db.set_value(..., "bill_status", ...)` in `bill_approval_sync.py` writes to directly, which is a plain column write that never goes through `frappe.model.workflow.validate_workflow` (that check only runs inside a full `doc.save()`, and `frappe.db.set_value` bypasses it entirely). Almost everything in this engine uses `frappe.db.set_value` for exactly that reason — it's how the engine gets to move the ticket through states the configured Workflow doesn't define an explicit linear edge for.

The two places in this file that use `ticket.save()` instead — `close_zero_amount_tax_invoice_bill`'s ticket-closing branch (§6) — **do** go through `validate_workflow`, which is precisely why they need `ticket.flags.ignore_workflow_transition = True` (a flag this codebase added; it is not a Frappe built-in). Any *new* code that calls `.save()` on the ticket to set `bill_status` needs to make the same call: either the Workflow already defines a legal edge for that specific transition, or the flag is required.

All of the approval-chain enforcement in this file (which bill unlocks which ticket state) is **hand-rolled application logic** layered on top of that Workflow, not driven by it. `crm.api.workflow.execute_workflow_action`, by contrast, *does* drive the real Frappe Workflow directly (via `apply_workflow`, checking `transition.allowed` against the current user's roles) for the actions the frontend triggers on the ticket (e.g. "Submit for MM Review", "Approve", "Reject" button clicks). Both mechanisms write the same `bill_status` field — they're two drivers of one state machine, not two separate ones.

---

## 9. Adjacent files (one paragraph each)

- **`tax_invoice_adherence.py`** — `validate_tax_invoice_fe_approval(doc)` blocks an FE's Approve click on a Tax Invoice bill when its amount falls outside `lower_percent`–`upper_percent` (default 80%–105%, configurable via Global Config `maintenance_ops_config.tax_invoice_adherence`) of the Admin Approved Pre Invoice total. It only fires on a genuine transition into `"FE Approved"`, same pattern as §6. `validate_billing_upload_allowed(doc)` separately blocks any *new* bill upload once a ticket already has a Finance Approved Tax Invoice.
- **`finance_approval_sync.py`** — `sync_finance_approval_to_linked_bills` pushes `finance_approval_status` onto every bill on a ticket once the ticket's `bill_status` reaches a finance-relevant state, **excluding any bill whose own resolved status is `"Closed"`** (fixed 2026-09-29, see Recent fixes item 2); `finance_approval_for_workflow_state` is the ticket-state → finance-status mapping table.
- **`maintenance_bill.py`** (doctype controller) — housekeeping only: field normalization, part-row cleanup for non-Tax-Invoice bills. Deliberately contains none of the approval-chain logic — that all lives in `bill_approval_sync.py`, wired up as the `on_update` hook.
- **`maintenance_ticket.py`** (doctype controller) — `validate_workflow()` skips the base Frappe Workflow-transition check on insert (`flags.in_insert`) and now also when `flags.ignore_workflow_transition` is set (added 2026-09-29, see §6/§8); `on_update` calls `_sync_finance_approval_to_bills_if_needed`, which is the ticket-level trigger for `sync_finance_approval_to_linked_bills` above — this is the exact call site that can stamp `finance_approval_status` onto a not-yet-closed zero-amount bill.
- **`bill_approval_config.py`** — reads/writes the configurable amount-bracket thresholds (`Maintenance Auto Approval Settings` doctype) that `apply_auto_approval_for_bracket` checks against.
- **`pms_cycle_reset.py`** — `maybe_pms_cycle_reset_on_bill_approved` fires the external portal cycle-reset call the first time a bill enters the approved chain; `did_bill_just_enter_approved` is the transition-detection helper `_bill_just_entered_approved` in `bill_approval_sync.py` delegates to.
- **`crm/api/workflow.py`** — `execute_workflow_action` is the real Frappe Workflow driver (see §8); it's what the frontend calls for every Approve/Reject button click on the ticket itself.
- **`crm/api/maintenance_bill_helpers.py`** — `_route_bill_approval_assignment_impl` reassigns the ticket to the next approver's email whenever the ticket's `bill_status` changes (hub-based lookup, or role-based hardcoded fallback emails from site config).
- **`crm/api/maintenance_api.py`** — `update_maintenance_ticket` is the generic "patch this ticket's fields" endpoint; its actual fetch+apply+save logic lives in `_update_maintenance_ticket_once`, wrapped in `crm.utils.retry.retry_on_timestamp_mismatch` so a concurrent edit to the same ticket retries against the freshly-fetched row instead of failing outright. `recalculate_bill_approval_statuses` re-applies bracket rules and re-syncs the ticket for a given `bill_type` — see Recent fixes item 3 for the missing-argument bug that made it a no-op on every call until 2026-09-29.
