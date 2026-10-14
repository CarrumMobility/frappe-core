# Bill Approval Engine — Frontend Function Walkthrough

> **Scope:** A function-by-function reference for the frontend "engine" files that
> derive approval-chain gate positions and drive the ticket workflow state from
> per-bill statuses. This doc complements — it does not repeat —
> [`bill_approval_flows.md`](../../../crm/docs/bill_approval_flows.md) (the end-to-end UI/API
> flow, "what happens when the user clicks Approve") and
> [`MAINTENANCE_MODULE.md`](../../../crm/docs/MAINTENANCE_MODULE.md) (the whole module). Where
> useful, this doc points at the exact step in `bill_approval_flows.md` a
> function participates in.
>
> **Companion doc:** [`bill_approval_engine_backend.md`](./bill_approval_engine_backend.md) — the Python engine this file mirrors.
> **Product-facing doc:** [`../product/bill_approval_engine.md`](../product/bill_approval_engine.md) — what all of this looks like on screen.
>
> **Why this doc exists:** these files are a deliberate JS mirror of the Python
> engine in `apps/crm/crm/module_maintenance/bill_approval_sync.py`. The two
> sides can drift, and the gate-index arithmetic (`getBillNextGateIndex` in
> particular) is easy to misread. Every function below names its Python
> counterpart where one exists, and includes at least one worked numeric
> example.
>
> Relocated 2026-09-29 from `apps/crm/docs/` to the `apps/core/docs/technical` convention.

---

## Recent fixes (2026-09-29)

The previous version of this doc described the bugs below as *intentional design* — it was wrong. If anything else in this doc (or in code comments) still says "Closed means gate index 0" or similar, treat it as stale and prefer this section.

1. **`getBillNextGateIndex('Closed', 'Tax Invoice')` used to return `0`, not `chain.length`.** `'Closed'` was grouped into the same early-exit bucket as `'Pending'`/`'active'`/`'completed'` — i.e. "hasn't started" — instead of being recognized as the terminal, fully-cleared state it actually is for a Tax Invoice bill (the Python side always treated it this way, see `bill_approval_engine_backend.md` §3). This single wrong index cascaded into every function built on top of it (`getTargetTicketWorkflowState`, `allTaxInvoicesPastApprovalChain`, `syncMaintenanceTicketWorkflowFromBills`, ...), which is why a closed zero-amount bill kept getting treated as if it had just reset to the very start — repeatedly forcing the ticket back to `"FE Pending (TI)"` after the backend had correctly closed it. Fixed: Tax Invoice `'Closed'` now returns `chain.length`, matching Python.
2. **`resolveBillDocStatus` (in `BillTypeSection.vue`, not `billWorkflowSync.js` — see that section below) had a hardcoded `return 'Pending'` fallback** for any status that isn't in `PERSISTABLE_BILL_STATUSES` — which `'Closed'` deliberately is not (see `isPersistableBillStatus` below). Since both the column and JSON values legitimately agree on `'Closed'` once a bill is closed, this function's first two branches don't fire, and it fell through to that hardcoded default — silently turning a genuinely `'Closed'` bill back into `'Pending'` on screen. Fixed to fall back to the real value (`shellSt || jsonSt || 'Pending'`), matching the Python resolver's fallback exactly (see `bill_approval_engine_backend.md` §2).
3. **`getTargetTicketWorkflowState` and `getDisplayTicketWorkflowStateForTicket` unconditionally returned `"Finance Approved"`** whenever every Tax Invoice bill had cleared its gate — with no check for whether that "clearing" happened via a literal `"Closed"` bill. Once fix 1 above made `'Closed'` correctly count as "gate cleared" for the first time, this bug became newly *visible*: the ticket's top badge started showing "Finance Approved" instead of "Closed" (previously it accidentally showed something else, for the wrong reason). Fixed both functions to check for a literal `'Closed'` bill among the fully-cleared ones and return `'Closed'` instead.
4. **`ensureTicketAtFinanceApproved` force-set the ticket to `"Finance Approved"`** any time `allTaxInvoicesPastApprovalChain` was true, without checking if the ticket was already sitting at `"Closed"` — same root issue as #3, different call site. Fixed with an early-return when the ticket is already `'Closed'`.

**Net effect of #1–#4 together:** before 2026-09-29, approving a zero-amount Tax Invoice bill would show the toast `"Bill approved (Pending)."`, the bill row would keep showing `"Pending"`, and the ticket's badge would show `"Finance Approved"` — none of which reflected the backend's actual (correct) state of `bill_status = "Closed"` on both documents. All four symptoms had the *same underlying cause* even though they look like three unrelated bugs.

5. **(Later the same day) `getTargetTicketWorkflowState` and `getDisplayTicketWorkflowStateForTicket` used `bills.some(status === 'Closed')`, not `.every(...)`.** Fix #3 above correctly stopped relabelling a fully-cleared Tax Invoice chain as `"Finance Approved"` when it contained a `'Closed'` bill — but with `some()`, a ticket with **one** zero-amount `'Closed'` bill and **one** genuinely `'Finance Approved'` bill also came out `'Closed'`, hiding the real finance sign-off (reported against ticket MNT-32634). Changed both functions to `.every(...)`: the ticket only reads `'Closed'` when *every* Tax Invoice bill got there via the zero-amount shortcut; a mix returns `'Finance Approved'`. The Python side got the matching `all()` fix (see `bill_approval_engine_backend.md` Recent fixes #4).

---

## Files covered

| File | Role |
|---|---|
| `helpers/billWorkflowSync.js` | Per-bill gate index + ticket-workflow-state derivation ("what state should the ticket be in, given these bills") |
| `constants/approvalChainConfig.js` | The chain definitions themselves (Pre Invoice 5-gate, Tax Invoice 2-gate), persistable-status set, role/permission helpers |
| `helpers/billAutoApproval.js` | Amount-bracket auto-approval skip (small bills jump straight to Admin Approved) |
| `composables/billSection/useBillWorkflow.js` | Composable version of Approve/Reject/Save handlers — **see the "Two implementations" note below, this is currently unused by the live UI** |
| `pages/ticket-detail/components/billing/BillTypeSection.vue` | The component that actually wires Approve/Reject/Save to the engine (its own inline copies of the handlers above), **and** its own separate `resolveBillDocStatus`/`mergeBillRowShellWithJson` merge logic for the bill table (see new section below) |
| `pages/ticket-detail/components/billing/BillReviewModal.vue` | The modal that computes gate/permission state for display and emits `save` / `approve` / `reject` |

`composables/billReview/useBillReviewCalculations.js` (invoice totals/GST/TDS
math) is **not** covered here in depth — it is bill arithmetic, not
approval-chain logic. `BillReviewModal.vue` computes its own totals inline instead.

---

## Important gotcha: two implementations of Approve/Reject/Save

`composables/billSection/useBillWorkflow.js` exports `useBillWorkflow(deps)`,
which returns `handleApprove`, `handleReject`, `handleSaveReview`, etc. It
looks like the natural place to look for "what happens on Approve." **It is
not used anywhere.** A repo-wide search for `useBillWorkflow(` turns up only
its own `export function useBillWorkflow(deps) {` declaration — no component
calls it.

The component actually wired to the UI, `BillTypeSection.vue`, defines its own
`handleSaveReview`, `handleApprove`, `handleReject` inline (search for
`@save="handleSaveReview"` / `@approve="handleApprove"` / `@reject="handleReject"`
in its template). These are near-line-for-line copies of the
composable's functions, but they are a **separate copy** — editing one does not edit the other.

**Practical implication:** if you're chasing a live approval bug, the code
that ran is in `BillTypeSection.vue`. Use `useBillWorkflow.js` as a reference
implementation / for comparison, but don't expect a fix there to take effect
until `BillTypeSection.vue` is either fixed too or refactored to delegate to
the composable. (The gate-index/status-resolution bugs in the Recent Fixes
section above live in shared files — `billWorkflowSync.js` and
`approvalChainConfig.js` — so those fixes apply to both copies at once. The
`resolveBillDocStatus` bug did not: it's a `BillTypeSection.vue`-local
function with no composable equivalent.)

---

## `constants/approvalChainConfig.js`

### The chains: `MAINTENANCE_BILL_APPROVAL_CHAIN`, `TAX_INVOICE_APPROVAL_CHAIN`, `APPROVAL_CHAINS`

Two ordered arrays of gate definitions:

```
Pre Invoice (5 gates): FE → MM → FGM → SGM → Admin
Tax Invoice (2 gates): FE → Finance
```

Each entry is `{ role, label, pendingState, approveAction, rejectAction }`.
`APPROVAL_CHAINS = { 'Pre Invoice': ..., 'Tax Invoice': ... }` is the lookup
every other function in this doc uses via `APPROVAL_CHAINS[billType]`.

**Array order is the gate index.** `chain[0]` is gate 0, `chain[1]` is gate 1,
etc. This is exactly the number `getBillNextGateIndex` (below) returns and
`getCurrentApprovalIndex` looks up — reordering these arrays silently
renumbers every gate everywhere.

No Python file defines these exact arrays (the workflow states themselves
live in the Frappe Workflow doctype, `Fleet Maintenance Approval New` — see
`bill_approval_flows.md`'s "Frappe Workflow" section), but
`bill_approval_sync.py` encodes the same 5-gate / 2-gate structure in its own
constants, and both must agree on `pendingState` strings.

### `isPersistableBillStatus(status)` / `PERSISTABLE_BILL_STATUSES`

The allow-list of `bill_status` values considered "a real, meaningful gate
state" — the base doc statuses (`Pending`, `Approved`, `Rejected`, `active`,
`completed`) plus every `{role} Approved` / `{role} Rejected` generated from
both chains. Deliberately **excludes** values like `Closed` or
`Ops Pending` — those are valid `bill_status` values in other contexts, but
they don't tell you which approval gate a bill is sitting at, so treating them
as "persistable" would corrupt the status-resolution logic in
`resolveBillStatusFromMaintenanceRow` (see below).

**Example:** `isPersistableBillStatus('MM Approved')` → `true` (generated from
the Pre Invoice chain's MM role). `isPersistableBillStatus('Closed')` →
`false`, even though `Closed` is a real value a Tax Invoice bill can have.

**This exclusion is intentional and correct** — the bug (Recent Fixes #2)
was never that `'Closed'` should be added to this set; it was that the
*fallback* for "not in this set" incorrectly defaulted to `'Pending'`
instead of the real value. Don't "fix" this bug by adding `'Closed'` here —
that would silently change what "persistable" means for every other caller
of `isPersistableBillStatus` (including the resolution-order rule 1 in
`resolveBillStatusFromMaintenanceRow`, which specifically depends on
`'Closed'` *not* being persistable).

### `roleApprovedBillStatus(role)` / `roleRejectedBillStatus(role)`

Trivial string builders: `roleApprovedBillStatus('FE')` → `'FE Approved'`,
`roleRejectedBillStatus('MM')` → `'MM Rejected'`. Exists so the "per-gate
approved/rejected status" spelling is defined in exactly one place — every
other function (`getBillNextGateIndex`, `handleApprove`, `handleReject`)
builds/matches these strings through this function rather than
string-concatenating inline.

### `billStatusAfterGateApproval(level, currentBillStatus)`

Given the gate just cleared and the bill's current status, returns the new
`bill_status` to persist. Almost always `roleApprovedBillStatus(level.role)`,
with one carve-out: when `level.approveAction === 'Submit for Finance Review'`
(the Tax Invoice FE gate), the bill does **not** move to a "Submit for Finance
Review"-flavored status — that action is a *ticket*-level transition only.
The bill stays `FE Approved` until Finance actually acts on it (unless it's
already `Finance Approved`, in which case it's left alone).

**Example:** `billStatusAfterGateApproval({ role: 'FE', approveAction: 'Submit for Finance Review' }, 'Pending')`
→ `'FE Approved'` (not some nonexistent "Submitted" status).
`billStatusAfterGateApproval({ role: 'MM', approveAction: 'Approve' }, 'FE Approved')`
→ `'MM Approved'`.

### `canUserEditBill(workflowState, billType, userRoles)`

Permission check: can this user edit/approve a bill sitting at
`workflowState`? Privileged roles (`isMaintenancePrivilegedUser`) always pass.
`Reconcile Pending` is a special case gated by `COMMERCIAL_RECONCILE_ROLES`
(Commercial + admins) rather than the approval-chain role hierarchy, because
reconcile is Flow 2 in `bill_approval_flows.md`, a separate path that bypasses
the chain entirely. Otherwise it resolves which role owns this
`workflowState` (`getEditableRole`) and checks the user has that role — for
Pre Invoice roles, `ROLE_HIERARCHY` lets a HIGHER role also edit a LOWER
gate's state (an SGM can act at an MM Pending gate), matching "escalation
should never lock someone out of their own team's earlier work."

---

## `helpers/billWorkflowSync.js`

This file's own header comment states the central rule: *"The ticket sits at
the gate of the bill that is furthest behind; other bills keep their own
status while the lagging bill catches up."* Every function below either
computes "how far behind is this one bill" or "given all bills, what should
the ticket's state be."

### `getBillNextGateIndex(billStatus, billType = 'Pre Invoice')` — the function this doc was originally requested for

Python counterpart: **`get_bill_next_gate_index`** in `bill_approval_sync.py`.

**What it returns:** a count of gates this bill has *cleared*, not "the gate
it's currently sitting at" — `0` means "hasn't cleared gate 0 yet" (still at
FE), and a value equal to `chain.length` means "cleared every gate in this
chain." This is why callers compare with `>= chain.length` to mean "fully
done," and index `chain[idx]` to mean "the gate still pending."

**Step-by-step:**

1. Look up the chain for `billType`. If there's no chain (`chain?.length` is
   falsy), return `0` immediately.
2. Trim the status to a string `s`.
3. **Early exit 1** — if `s` is empty, or one of `'Pending'`, `'active'`,
   `'completed'`, return `0`.
4. **Early exit 1b (Tax Invoice only)** — if `billType === 'Tax Invoice'` and
   `s === 'Closed'`, return `chain.length` — **fully cleared**, not "not
   started" (fixed 2026-09-29; see Recent fixes #1). A Tax Invoice bill can be
   `'Closed'` via the zero-amount rule or an inhouse-workshop close, and both
   mean the bill needs nothing further from anyone.
5. **Early exit 2** — if `s === 'Rejected'` or `s` ends with `' Rejected'`,
   return `0`. **This is the single most important thing to remember about
   this function: rejection does not preserve gate progress.** An
   `'SGM Rejected'` bill — which had cleared FE, MM, and FGM before SGM
   rejected it — returns `0` here, not `3`. The bill (and the ticket) restarts
   from the very first gate.
6. **Main scan** — loop over every gate in the chain, and remember the
   **highest** index `i` where `s === roleApprovedBillStatus(chain[i].role)`.
   Using the highest match (rather than stopping at the first) matters for Tax
   Invoice's `'Finance Approved'`, which must be recognized as "past Finance
   Pending" and not confused with an unrelated earlier match.
   - If a match was found, return `highestApprovedIdx + 1`.
7. **Legacy fallback** — if `s === 'Approved'` (a bare, role-less legacy
   value from before per-gate statuses existed), return `1`.
8. Otherwise return `0`.

**Worked examples:**

- `getBillNextGateIndex('', 'Pre Invoice')` → `0` (empty status, early exit 1).
- `getBillNextGateIndex('Pending', 'Pre Invoice')` → `0` (early exit 1).
- `getBillNextGateIndex('FE Approved', 'Pre Invoice')` → chain is
  `[FE, MM, FGM, SGM, Admin]`. `roleApprovedBillStatus('FE')` is
  `'FE Approved'`, matched at `i = 0`. Returns `0 + 1 = 1` — "cleared 1 gate
  (FE), next gate is MM (index 1 in the chain)."
- `getBillNextGateIndex('FE Approved', 'Tax Invoice')` → chain is
  `[FE, Finance]`. Matched at `i = 0`. Returns `1` — "cleared the FE gate,
  next gate is Finance (index 1)."
- `getBillNextGateIndex('Admin Approved', 'Pre Invoice')` → matched at
  `i = 4` (Admin is the last of 5 gates, index 4). Returns `5`, which
  equals `chain.length` — the bill has cleared every gate in this chain.
- `getBillNextGateIndex('SGM Rejected', 'Pre Invoice')` → early exit 2 fires.
  Returns `0`, **not** `3`, even though the bill had previously cleared FE,
  MM, and FGM to reach the SGM gate. Progress is discarded on rejection.
- `getBillNextGateIndex('Closed', 'Tax Invoice')` → early exit 1b fires
  (as of 2026-09-29). Returns `chain.length` (`2`) — **fully cleared**. This
  is what a zero-net-amount Tax Invoice bill looks like after the backend
  closes it. **Before the 2026-09-29 fix this returned `0`** — see Recent
  fixes #1 for why that was wrong and what it broke.
- `getBillNextGateIndex('Closed', 'Pre Invoice')` → `'Closed'` is not
  special-cased for Pre Invoice (mirrors the Python side, which also has no
  Pre-Invoice equivalent — see `bill_approval_engine_backend.md` §3). Falls
  through the main scan (no role's approved-status string is `'Closed'`),
  then the legacy fallback (not `'Approved'`), to `0`. In practice a Pre
  Invoice bill should never actually be `'Closed'`.
- `getBillNextGateIndex('Approved', 'Pre Invoice')` → doesn't match any
  `roleApprovedBillStatus`, falls through to the legacy fallback. Returns `1`.

### `getEffectiveApprovalGateIndex(billStatus, billType, ticketWorkflowState)`

`Math.max(getBillNextGateIndex(billStatus, billType), getCurrentApprovalIndex(ticketWorkflowState, billType))`.

**Why the max, not just the bill's own index:** for Tax Invoice specifically,
the *ticket* can be ahead of the *bill row*. FE approves (bill →
`'FE Approved'`), which fires the ticket-level `'Submit for Finance Review'`
workflow action, moving the ticket to `'Finance Pending'` — but the bill row
itself is untouched (per `billStatusAfterGateApproval`'s carve-out above)
until Finance acts. Taking the ticket's index whenever it's ahead avoids
Finance/Admin appearing "locked out" of a gate the ticket already says is
active.

**Example:** `getEffectiveApprovalGateIndex('FE Approved', 'Tax Invoice', 'Finance Pending')`
→ bill index is `1`. Ticket index is `getCurrentApprovalIndex('Finance Pending', 'Tax Invoice')`
→ `1`. `Math.max(1, 1) = 1` — same answer here, but if the bill were still
`'Pending'` (index `0`) while the ticket is at `'Finance Pending'` (index `1`),
the result would still be `1`, keeping Finance's gate active.

### `canUserApproveAtBillGate(billStatus, billType, ticketWorkflowState, userRoles)`

Combines the gate index (using `getEffectiveApprovalGateIndex` for Tax
Invoice, plain `getBillNextGateIndex` for Pre Invoice) with
`canUserEditBill` from `approvalChainConfig.js` to answer "can this specific
user act right now." Privileged users always pass.

### `allBillsClearedGate(bills, gateIdx, billType, resolveBillStatus)`

`true` only if **every** bill's `getBillNextGateIndex(...) > gateIdx`. This is
the direct enforcement of "the ticket doesn't advance past a gate until every
bill has cleared it" — used before firing a ticket-level `approveAction` in
`handleApprove`.

**Example:** two Pre Invoice bills, one at `'MM Approved'` (index 2) and one
at `'FE Approved'` (index 1). `allBillsClearedGate(bills, 1, 'Pre Invoice', ...)`
→ Bill A: `2 > 1` ✓. Bill B: `1 > 1` ✗. Returns `false` — the ticket cannot
advance past the MM gate (index 1) yet.

### `getTargetTicketWorkflowState(bills, billType, resolveBillStatus)`

Python counterpart: **`get_target_ticket_workflow_from_tax_invoice_bills` /
`get_target_ticket_workflow_from_maintenance_bills`** (`bill_approval_sync.py`).

Computes `getBillNextGateIndex` for every bill, takes `Math.min(...)` of the
results, and maps that minimum index back to `chain[minIdx].pendingState`.
If the minimum is `>= chain.length` (every bill has cleared every gate),
there's no `pendingState` to point at anymore:

- **Pre Invoice** → returns `TICKET_STATE_AFTER_MAINTENANCE_BILL_CHAIN` (`'FE Pending (TI)'`).
- **Tax Invoice** → returns `TICKET_STATE_AFTER_TAX_INVOICE_CHAIN` (`'Finance Approved'`) — **unless every one of the fully-cleared bills is literally `'Closed'`**, in which case it returns `'Closed'` instead (fixed 2026-09-29, tightened from `.some()` to `.every()` later the same day — see Recent fixes #3 and #5; mirrors the Python override in `bill_approval_engine_backend.md`).

```js
if (minIdx >= chain.length) {
  if (billType === 'Pre Invoice') return TICKET_STATE_AFTER_MAINTENANCE_BILL_CHAIN
  if (billType === 'Tax Invoice') {
    const allClosed = bills.every((b) => String(resolveBillStatus(b) ?? '').trim() === 'Closed')
    return allClosed ? 'Closed' : TICKET_STATE_AFTER_TAX_INVOICE_CHAIN
  }
  return null
}
return chain[minIdx].pendingState
```

**Worked example:** three Pre Invoice bills with statuses `'MM Approved'`
(index 2), `'FE Approved'` (index 1), `'Admin Approved'` (index 5). Indices:
`[2, 1, 5]`. `minIdx = 1`. `chain[1].pendingState` = `'MM Pending'`. The ticket
should be at `'MM Pending'` — waiting on the FE-Approved-only bill to clear
MM — even though one bill has already finished the entire chain.

**Worked example (the fixed case):** one Tax Invoice bill, zero-amount,
closed via the backend rule (`resolveBillStatus` → `'Closed'`). Index:
`getBillNextGateIndex('Closed', 'Tax Invoice')` → `2` (`chain.length`, per the
2026-09-29 fix). `minIdx = 2 >= chain.length` → check `allClosed`: only one
bill, and it's `'Closed'`, so yes → returns `'Closed'`. **Before the fix**,
step one alone (`getBillNextGateIndex`
returning `0` for `'Closed'`) meant `minIdx = 0`, so this function returned
`chain[0].pendingState = 'FE Pending (TI)'` instead — the ticket badge would
show the bill as having made *zero* progress, right after the backend had
just closed it.

### `resolveBillStatusFromMaintenanceRow(row)`

Python counterpart: **`resolve_bill_status_from_row`**.

A bill's real status can live in two places that can disagree: the
`bill_status` column, and a nested `bill_status` key inside the
`vendor_parser_data` JSON blob (which the frontend rewrites wholesale on every
approve/reject/save). Resolution:

1. If both are set, differ, **and both are persistable**
   (`isPersistableBillStatus`), the **JSON value wins**.
2. Otherwise, whichever one is persistable wins (a non-persistable value like
   `'Closed'` loses to a persistable one even if it's "newer," because it
   doesn't identify a gate).
3. Fallback: `shellSt || jsonSt || ''` — **this function's fallback was
   always correct.** The bug (Recent fixes #2) is in a *different*,
   similarly-named function — `resolveBillDocStatus` in `BillTypeSection.vue`
   — whose fallback was wrong. Do not confuse the two; see the dedicated
   section below.

**Worked example:** `row.bill_status = 'Closed'`,
`row.vendor_parser_data = '{"bill_status":"FE Approved", ...}'`. Column value
`'Closed'` is not persistable; JSON value `'FE Approved'` is persistable.
Step 1 doesn't apply. Step 2: `'FE Approved'` is persistable, so it wins.
Returns `'FE Approved'`.

**Worked example (both sides agree on Closed):** `row.bill_status = 'Closed'`,
JSON `bill_status` also `'Closed'`. Neither is persistable, so steps 1 and 2
don't fire; step 3's fallback returns `shellSt` = `'Closed'` — correctly.

### `getDisplayTicketWorkflowState(...)` / `getDisplayTicketWorkflowStateForTicket(...)`

Display-only variants: what should the UI *show* as the ticket's workflow
state, given the stored value might be stale or the ticket might have run
ahead. `getDisplayTicketWorkflowStateForTicket` (used for the ticket header
badge) additionally arbitrates between Pre Invoice and Tax Invoice bills on
the same ticket — Tax Invoice completion (`allTaxInvoicesPastApprovalChain`)
overrides showing a Pre Invoice-driven state once TI bills exist and are
done, **but as of 2026-09-29 checks whether every Tax Invoice bill is
literally `'Closed'`** (Recent fixes #3, tightened by #5) instead of
unconditionally returning `'Finance Approved'`:

```js
if (taxInvoiceBills?.length && allTaxInvoicesPastApprovalChain(taxInvoiceBills, resolveBillStatus)) {
  const allClosed = taxInvoiceBills.every((b) => String(resolveBillStatus(b) ?? '').trim() === 'Closed')
  return allClosed ? 'Closed' : TICKET_STATE_AFTER_TAX_INVOICE_CHAIN
}
```

### `syncMaintenanceTicketWorkflowFromBills(ticketName, billType, currentWorkflowState, bills, resolveBillStatus, { allowAdvance })`

Python counterpart: **`sync_maintenance_ticket_workflow_from_bills`**.

The reconciliation loop: repeatedly computes the bill-implied target state
(`getTargetTicketWorkflowState`) and either force-sets the post-chain
terminal state, force-aligns the ticket **backward** if it has drifted ahead
of what the bills actually support, or (only when `allowAdvance` is true)
fires the current gate's `approveAction` to step the ticket **forward** one
gate at a time. Capped at `chain.length * 2` iterations as a safety valve.

As of 2026-09-29, the Tax Invoice terminal-state branch also accepts
`target === 'Closed'` (not just `TICKET_STATE_AFTER_TAX_INVOICE_CHAIN`), so a
ticket that's lagging behind a bill that's already `'Closed'` gets forced to
`'Closed'`, not `'Finance Approved'` (Recent fixes #3, same override as
`getTargetTicketWorkflowState` above — this loop just needed to recognize the
new possible target value too).

### `ensureTicketAtTaxInvoiceGate` / `ensureTicketAtFinanceApproved`

Thin wrappers that force the ticket to the fixed post-chain state
(`'FE Pending (TI)'` or `'Finance Approved'`) if it isn't already there.
`ensureTicketAtFinanceApproved` is called once all Tax Invoice bills have
cleared their chain (`allTaxInvoicesPastApprovalChain`) — which, since the
2026-09-29 fix, is also true for an all-`'Closed'` chain. **As of 2026-09-29
it early-returns if the ticket is already `'Closed'`** instead of
force-overwriting it to `'Finance Approved'` (Recent fixes #4):

```js
const wf = String(ticket?.bill_status ?? '').trim()
if (wf === TICKET_STATE_AFTER_TAX_INVOICE_CHAIN || wf === 'Closed') return wf
```

---

## `helpers/billAutoApproval.js`

### `computeMaintenanceBillAutoStatus(oldStatus, newStatus, netAmount, thresholds, billType)`

Python counterpart: **`apply_auto_approval_for_bracket`** /
**`apply_maintenance_bill_approval_rules`** (`bill_approval_sync.py`).

**Why it exists:** below a configurable amount threshold for the gate a bill
is at, the bill shouldn't need every remaining approver to sign off — it
jumps straight to `'Admin Approved'`. Documented with default thresholds in
`bill_approval_flows.md` step 4 (FE ₹5,000 / MM ₹10,000 / FGM ₹15,000 / SGM
₹20,000).

**Pre Invoice only** — the function's first line checks `billType`, and for
`'Tax Invoice'` it returns `newStatus` unchanged with no bracket logic at all.
A Tax Invoice bill must always go through an explicit Finance approval (or the
zero-amount closure rule); it can never legitimately skip to a terminal
status by amount bracket alone.

**Logic for Pre Invoice:**

- If `statusAdvanced(oldStatus, newStatus)` is true (a genuine forward step):
  look up the bracket threshold for the gate **being left** (`oldStatus`). If
  `oldStatus` has no bracket, fall back to the bracket for the gate **being
  entered** (`newStatus`).
- If not a forward step (e.g. just an amount edit with the status unchanged):
  check `newStatus`'s own bracket directly.
- In both cases, if `amount <= threshold`, return `'Admin Approved'` instead
  of `newStatus`.

**Worked example (mirrors the one in `bill_approval_flows.md` step 4):** FE
approves a bill with net amount ₹6,000.

1. `computeMaintenanceBillAutoStatus('Pending', 'FE Approved', 6000, null, 'Pre Invoice')`
   — forward step. Bracket for `'Pending'` doesn't exist, falls back to
   `'FE Approved'`'s bracket (₹5,000). `6000 > 5000` → not auto-approved.
   Returns `'FE Approved'`.
2. MM later approves: bracket for the gate being left (`'FE Approved'`,
   ₹5,000) is used. `6000 > 5000` → still not auto-approved. Returns
   `'MM Approved'`.
3. FGM approves next: bracket for `'MM Approved'` (₹10,000). `6000 <= 10000`
   → **auto-approval triggers**. Returns `'Admin Approved'` — the bill skips
   the FGM/SGM gates entirely once MM has cleared it and the amount is small
   enough for MM's bracket.

### `resolveBillNetAmount(bill)`

Priority order for "what amount do we check against the bracket": explicit
`net_payable` (FE-edited) > `amount` > amounts inside the
`vendor_parser_data` JSON blob (`net_payable`/`net_amount`/`amount`/`total_amount`)
> the `net_amount` column (can be stale right after OCR) > `0`.

### `cumulativePreInvoiceTotal(bills, { excludeName, thisAmount })`

Optimistic-UI-only mirror of the Python `_cumulative_pre_invoice_total`: sums
this bill's amount plus every other non-rejected Pre Invoice bill already
loaded for the same ticket, so that splitting one large bill into several
small ones can't dodge the auto-approval bracket check (even briefly, before
the server's authoritative re-check on save).

---

## `composables/billSection/useBillWorkflow.js`

See "Important gotcha" above — this composable is unused; its functions are a
reference copy of what `BillTypeSection.vue` actually runs.

- **`reconcileTicketWorkflowFromBillsIfNeeded()`** — guards against
  cross-phase contamination: a Pre Invoice section instance must not
  recompute the ticket's state from Pre Invoice bills if the ticket has
  already moved into the Tax Invoice phase (and vice versa).
- **`handleApprove(formData)`** — resolve gate → auto-approval bracket check
  → persist bill → re-fetch fresh sibling bills → advance ticket only if
  `allBillsClearedGate` (or privileged) → final
  `syncMaintenanceTicketWorkflowFromBills` catch-all. See
  `bill_approval_flows.md` steps 2-6.
- **`handleReject(formData)`** — always rolls the *ticket* back to the FE
  gate regardless of sibling bills' progress.
- **`handleSaveReview(formData)`** — re-pins `bill_status` to the prior
  persistable status after merging in form edits, so an edit can never
  accidentally promote the bill to the next gate.
- **`completeFeRejectedResubmit(merged, base, docName)`** — folds "FE fixes a
  rejected bill" and "FE approves it" into one request.

---

## `pages/ticket-detail/components/billing/BillTypeSection.vue`

Contains the **live** `handleSaveReview` / `handleApprove` / `handleReject`
(wired via `@save` / `@approve` / `@reject` on `BillReviewModal.vue` further
down the same template). Logic mirrors `useBillWorkflow.js` function-for-
function.

### The bill-table's *own* status merge: `resolveBillDocStatus` / `mergeBillRowShellWithJson` / `effectiveBillStatusFromRow`

This component has its own, separate implementation of the column-vs-JSON
merge described for `resolveBillStatusFromMaintenanceRow` above — **do not
assume fixing one fixes the other; they're two different functions with two
different bugs found on two different days:**

- **`resolveBillDocStatus(shellBill, jsonBill)`** — same three-rule shape as
  `resolveBillStatusFromMaintenanceRow`, but its rule-3 fallback used to be a
  bare `return 'Pending'`. This is the function responsible for Recent fixes
  #2: a `'Closed'` bill (not persistable, and both column/JSON legitimately
  agree on it) fell straight through rules 1 and 2 into that hardcoded
  default, so the Tax Invoice table row displayed `"Pending"` for a bill the
  backend had correctly closed. Fixed to `return shellSt || jsonSt || 'Pending'`.
- **`mergeBillRowShellWithJson(bill, jsonData)`** — calls `resolveBillDocStatus`
  to get `bill_status`, then spreads the JSON fields over the shell fields for
  everything else (`bill_no`, `bill_date`, `bill_url`, service type, ...).
  Used both when building `bills.value` for the table (`loadBills`) and by
  `effectiveBillStatusFromRow`.
- **`effectiveBillStatusFromRow(row)`** — thin wrapper: parses
  `row.vendor_parser_data` if present and calls `mergeBillRowShellWithJson`,
  otherwise falls back to the raw `row.bill_status`. This is the
  `resolveBillStatus` function passed into most of the `billWorkflowSync.js`
  functions above from within this component (gate index checks, permission
  checks, `allTaxInvoicesPastApprovalChain`, etc.) — so the #2 bug fed wrong
  data into all of those too, on top of directly corrupting the table's
  status badge.
- **`getBillStatusBadge(bill)`** — the actual badge renderer for the bill
  table's Status column. Reads `bill.bill_status` (already resolved by the
  merge above) and maps it to a label/theme. `'Closed'` doesn't match any of
  its explicit branches (`' Approved'`/`' Rejected'`/`'Pending'`/`'active'`/
  `'completed'`), so it falls through to the generic
  `{ label: __(s), theme: 'orange' }` — it displays the literal text
  `"Closed"`, just styled orange rather than a more fitting color. This is a
  cosmetic gap, not a bug that was fixed 2026-09-29 — worth a follow-up if a
  designer wants a dedicated "Closed" badge color.

### Debug logging

As of 2026-09-29, most of the `console.log("checking2...", ...)` /
`console.log('checking...', ...)` lines that used to be scattered through
`billWorkflowSync.js`, `BillTypeSection.vue`, and `useBillWorkflow.js` have
been removed. `useBillWorkflow.js` still uses a proper gated `billDbg(...)`
helper (not raw `console.log`) throughout — that one is intentional and
safe to leave. If you find a *new* raw `console.log("checking...")` while
reading this code, it is very likely leftover from a live debugging session,
not intentional instrumentation — check with whoever added it before
assuming it's load-bearing.

## `pages/ticket-detail/components/billing/BillReviewModal.vue`

Computes the same gate/permission state for display and to decide which
buttons are visible:

- **`approvalGateIdx`** — for Tax Invoice, uses `getEffectiveApprovalGateIndex`
  (bill-vs-ticket max) so Finance isn't locked out when the ticket has run
  ahead of the bill row; for Pre Invoice, uses `getBillNextGateIndex` directly.
- **`billNextGateIdx`** — the *raw* per-bill index (no ticket-lag adjustment),
  used only for the debug logger, not for permission decisions.
- **`currentApprovalIdx`** / **`canApprove`** / **`canReject`** — derive from
  `approvalGateIdx`, i.e. the effective (ticket-aware) index, which is what
  actually controls whether the Approve/Reject buttons render.
- **`handleApproveSubmit` / `handleRejectSubmit`** — build the payload
  (including `_approveAction` / `_rejectAction` taken from
  `approvalChain.value[currentApprovalIdx.value]`) and `emit('approve', ...)`
  / `emit('reject', ...)`, which `BillTypeSection.vue` listens for.

---

## What the backend rule looks like from here (post-2026-09-09 fixes)

The zero-net-amount Tax Invoice auto-close rule
(`bill_approval_sync.close_zero_amount_tax_invoice_bill`, Python-only — see
`bill_approval_engine_backend.md` §6) still has **no frontend equivalent, and
none is needed**: from the frontend's point of view, such a bill simply comes
back from the backend already at `bill_status = 'Closed'` after a refresh.

**What changed 2026-09-29 is that the frontend now reads that `'Closed'`
value correctly** (Recent fixes #1–#4 above) instead of misreading it as "not
progressed." Do not add Tax-Invoice-net-amount-zero *branching* logic to the
frontend to work around a display bug — if a bill or ticket shows the wrong
status again, the fix belongs in `getBillNextGateIndex` /
`resolveBillDocStatus` / the two ticket-target functions above, not in a new
special case layered on top of them.
