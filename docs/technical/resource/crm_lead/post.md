# CRM Lead — POST

**Route:** `POST /api/resource/CRM%20Lead`  
**See also:** [Resource API overview](../api.md) · [CRM Lead README](README.md) · [fields.md](fields.md)

---

## Create document

Insert a new CRM Lead via the REST resource layer.

### Request

```
POST /api/resource/CRM%20Lead
Content-Type: application/json
X-Frappe-CSRF-Token: <csrf_token>
```

### Required body fields

| Field | Type | Description |
|---|---|---|
| `mobile_no` | string | 10-digit Indian mobile; must be unique |
| `status` | string | `CRM Lead Status.name` (Link PK) |
| `primary_status` | string | Status bucket label (defaults to `NEW` in schema) |
| `secondary_status` | string | Sub-disposition label (defaults to `NEW`) |

### Recommended optional fields

| Field | Type | Description |
|---|---|---|
| `lead_name` | string | Display name |
| `email` | string | Validated email |
| `lead_type` | string | `LEAD` (default), `DRIVER`, or `VENDOR` |
| `source` | string | Source label |
| `source_id` | string | `CRM Lead Source.name` |
| `telecaller` | string | Frappe username (Link → User) |
| `hub_id` | string | Carrum hub UUID |
| `custom_hub_name` | string | Hub display name |
| `gender` | string | Link → Gender |
| `preferred_lang` | string | Language select value |

Any other writable field from [fields.md](fields.md) may be included.

### Auto-set fields (do not send)

| Field | Behaviour |
|---|---|
| `name` | Auto-assigned `AAAA0001`–`ZZZZ9999` unless pre-set via admin/webhook |
| `mask_mobile_no` | Computed from `mobile_no` on save |
| `document_status` | Computed from attached KYC documents |
| `owner`, `creation`, `modified` | Server-managed |

### curl — minimal create

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/resource/CRM%20Lead' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_name": "John Doe",
    "mobile_no": "9876543210",
    "status": "<crm_lead_status.name>",
    "primary_status": "New",
    "secondary_status": "New"
  }'
```

### curl — full create with source and hub

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/resource/CRM%20Lead' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_name": "Jane Doe",
    "mobile_no": "9123456780",
    "email": "jane@example.com",
    "lead_type": "LEAD",
    "status": "<crm_lead_status.name>",
    "primary_status": "New",
    "secondary_status": "New",
    "source": "Website",
    "source_id": "<crm_lead_source.name>",
    "telecaller": "tc.agent@example.com",
    "hub_id": "<hub-uuid>",
    "custom_hub_name": "Bengaluru Hub",
    "preferred_lang": "Hindi"
  }'
```

### Response

```json
{
  "data": {
    "name": "AAAA0042",
    "doctype": "CRM Lead",
    "lead_name": "John Doe",
    "mobile_no": "9876543210",
    ...
  }
}
```

### Errors

| Error | Cause |
|---|---|
| `ValidationError` — duplicate mobile | `mobile_no` already exists |
| `ValidationError` — invalid phone | Not a valid 10-digit Indian mobile |
| `ValidationError` — missing status | `status` or status fields not set |
| `403` | No create permission |

---

## Preferred alternative — `create_lead` method

For SPA, referral, and telecaller flows, use the method API instead of raw POST. It handles:

- Phone normalization (`normalize_crm_lead_india_phone`)
- Default CRM Lead Status when `status` omitted
- Structured duplicate error: `CRM_DUPLICATE_LEAD|Lead|AAAA0001`

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.create_lead' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_name": "Jane Doe",
    "mobile_no": "9876543210",
    "source": "Employee Referral",
    "source_id": "<crm_lead_source.name>",
    "status": "<crm_lead_status.name>"
  }'
```

Full parameter list: [methods.md#create_lead](methods.md#create_lead).

---

## Alternative — `frappe.client.insert`

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/frappe.client.insert' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "doc": {
      "doctype": "CRM Lead",
      "lead_name": "John Doe",
      "mobile_no": "9876543210",
      "status": "<crm_lead_status.name>",
      "primary_status": "New",
      "secondary_status": "New"
    }
  }'
```

---

## Pre-fetch next lead ID (optional)

To reserve a specific display ID before insert (admin tooling):

```bash
# Peek next ID (does not consume)
curl -b cookies.txt 'https://<your-site>/api/method/crm.api.lead.get_next_lead_id'
```

Portal webhook `core.api.carrum_drivers.lead_creation_webhook` creates leads with portal-assigned IDs — see [methods.md](methods.md).

---

## Related

- [GET — read](get.md)
- [PUT — update](put.md)
- [Method APIs](methods.md)
