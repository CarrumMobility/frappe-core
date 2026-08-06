# Lead walkin done — POST

**Route:** `POST /api/resource/Lead%20walkin%20done`  
**See also:** [README](README.md) · [fields.md](fields.md)

---

## Create document (direct REST)

Insert a walk-in audit record via REST. **In production, use `take_lead_actions` instead** — it runs validation, updates the parent CRM Lead, creates events, and sets `walkin_form_link`.

### Request

```
POST /api/resource/Lead%20walkin%20done
Content-Type: application/json
X-Frappe-CSRF-Token: <csrf_token>
```

### Body fields

| Field | Type | Required | Description |
|---|---|---|---|
| `lead` | string | Yes | CRM Lead `name` (display ID) |
| `lead_status_link` | string | Yes | `CRM Lead Status.name` |
| `primary_status` | string | No | Disposition snapshot |
| `secondary_status` | string | No | Sub-disposition snapshot |
| `source` | string | No | Source label |
| `remarks` | string | No | Agent comment |
| `callback_at` | datetime | No | Callback or visit datetime |
| `callback_type` | string | No | `Callback` or `Visit Date` |
| `telecaller` | string | No | Frappe username |
| `business_type` | string | No | Product interest; required in walk-in form UI for all primary statuses |
| `referrer_name` | string | No | Referral snapshot |
| `referrer_mobile_no` | string | No | |
| `referrer_user_link` | string | No | Frappe username |
| `created_by` | string | No | Defaults to session user |
| `walkin_form_filled_at` | datetime | No | Auto-set to `creation` if omitted |

### curl — direct create (admin/testing)

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/resource/Lead%20walkin%20done' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead": "AAAA0001",
    "lead_status_link": "<crm_lead_status.name>",
    "primary_status": "Interested",
    "secondary_status": "Walk-in Done",
    "source": "Walk In",
    "remarks": "Manual test record",
    "business_type": "Black",
    "created_by": "administrator"
  }'
```

### Response

```json
{
  "data": {
    "name": "f6g7h8i9j0",
    "doctype": "Lead walkin done",
    "lead": "AAAA0001",
    ...
  }
}
```

> Direct POST does **not** update `CRM Lead.walkin_form_link`, `hub_visit_status`, or create Callback/Visit Date events. Use the method API below for production.

---

## Preferred — `take_lead_actions` (mark_walk_in_done)

**POST** `/api/method/crm.api.lead.take_lead_actions`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lead_id` | string | Yes | CRM Lead `name` |
| `action` | string | Yes | `mark_walk_in_done` |
| `lead_status` | string | Yes | `CRM Lead Status.name` |
| `source` | string | Yes | Source label |
| `source_pk` | string | No | `CRM Lead Source.name` |
| `remarks` | string | Conditional | When status requires remarks |
| `lead_name` | string | Conditional | When status requires name |
| `business_type` | string | Yes (UI) | Hub-scoped product interest; required for all primary statuses in the walk-in form. Server falls back to lead `business_type_name` if omitted. |
| `callback_datetime` | datetime | Conditional | Callback disposition |
| `scheduled_visit_date` | datetime | Conditional | Visit date disposition |
| `callback_type` | string | No | `Callback` or `Visit Date` |
| `telecaller` | string | Conditional | When source is telecaller |
| `hub_id` / `hub_name` | string | No | Hub assignment on LEAD |
| `referrer_name` | string | No | Referral source |
| `referrer_mobile_no` | string | No | |
| `referrer_user_link` | string | No | |
| `remind_before_minutes` | int | No | Default `0` |
| `expected_call_duration_minutes` | int | No | Default `5` |

### curl — standard walk-in submit

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.take_lead_actions' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_id": "AAAA0001",
    "action": "mark_walk_in_done",
    "source": "Google",
    "source_pk": "<crm_lead_source.name>",
    "lead_status": "<crm_lead_status.name>",
    "remarks": "Interested in rental",
    "business_type": "Black",
    "hub_id": "<hub-uuid>",
    "hub_name": "Bengaluru Hub"
  }'
```

### curl — with callback

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.take_lead_actions' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_id": "AAAA0001",
    "action": "mark_walk_in_done",
    "source": "Telecaller",
    "source_pk": "<crm_lead_source.name>",
    "lead_status": "<callback_status_pk>",
    "remarks": "Call back tomorrow",
    "callback_datetime": "2026-07-15 10:00:00",
    "callback_type": "Callback",
    "telecaller": "tc.agent@example.com",
    "business_type": "Black"
  }'
```

### curl — referral source

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.take_lead_actions' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_id": "AAAA0001",
    "action": "mark_walk_in_done",
    "source": "referrals",
    "source_pk": "<crm_lead_source.name>",
    "lead_status": "<crm_lead_status.name>",
    "remarks": "Referred by driver",
    "referrer_name": "Raj Kumar",
    "referrer_mobile_no": "9123456789",
    "business_type": "Black"
  }'
```

### Side effects (via method API)

1. Creates `Lead walkin done` record
2. Updates CRM Lead status (unless Drop/Converted)
3. Sets `source` / `source_id` on lead
4. Marks open Visit Date events Completed
5. Creates Callback or Visit Date event if datetime provided
6. Sets `hub_visit_status = HUB_VISITED`
7. Sets `walkin_form_filled_at`, `walkin_form_link`, increments `total_walkin_forms_filled`

Full flow: [Walk-in Form](../../walkin_form.md)

---

## Permissions

| Path | Roles |
|---|---|
| `take_lead_actions` | Onboarding, Telecaller Lead, Administrator |
| Direct REST POST | DocType create permission (System Manager + CRM agents via runtime perms) |

---

## Related

- [GET](get.md) · [PUT](put.md) · [DELETE](delete.md)
- [CRM Lead methods](../crm_lead/methods.md)
