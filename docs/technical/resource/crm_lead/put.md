# CRM Lead — PUT

**Route:** `PUT /api/resource/CRM%20Lead/{name}`  
**See also:** [Resource API overview](../api.md) · [CRM Lead README](README.md) · [fields.md](fields.md)

---

## Update document (partial)

Update an existing CRM Lead. The server loads the full document, merges only the supplied fields, runs validations (`validate()`), and saves.

### Request

```
PUT /api/resource/CRM%20Lead/{name}
Content-Type: application/json
X-Frappe-CSRF-Token: <csrf_token>
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Lead display ID (e.g. `AAAA0001`) |

### Body

JSON object with one or more writable field names. Omitted fields are unchanged.

### curl — update name and telecaller

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "lead_name": "John D.",
    "telecaller": "tc.agent@example.com"
  }'
```

### curl — update disposition

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "status": "<crm_lead_status.name>",
    "primary_status": "Interested",
    "secondary_status": "Callback",
    "last_remarks": "Will visit hub tomorrow"
  }'
```

### curl — update hub visit fields

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "hub_visit_status": "HUB_VISITED",
    "hub_id": "<hub-uuid>",
    "custom_hub_name": "Bengaluru Hub"
  }'
```

### curl — update KYC fields

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "aadhar_no": "123456789012",
    "pancard_number": "ABCDE1234F",
    "driving_license_number": "KA0120230012345",
    "bank_account_number": "123456789012",
    "bank_ifsc": "SBIN0001234"
  }'
```

### Response

Returns the updated document dict (same shape as GET single).

### Errors

| Error | Cause |
|---|---|
| `403` | No write permission |
| `404` | Lead not found |
| `ValidationError` | Business rule failed (see below) |
| `PermissionError` | Telecaller role restriction |

---

## Writable vs read-only fields

### Commonly updated

| Field | Notes |
|---|---|
| `lead_name` | Display name |
| `email`, `alternate_phone` | Contact |
| `status`, `primary_status`, `secondary_status` | Disposition; `status` Link synced on save |
| `last_remarks` | Agent comment |
| `telecaller`, `driver_manager` | Assignment |
| `source`, `source_id` | Attribution |
| `hub_id`, `custom_hub_name` | Hub |
| `hub_visit_status`, `gate_ticket_no` | Visit state |
| KYC / address fields | See [fields.md](fields.md) |
| `user_tags` | Per-user tag string (privacy merge on save) |

### Read-only / restricted

| Field | Reason |
|---|---|
| `name` | PK — use rename API if needed |
| `mask_mobile_no` | Computed |
| `document_status` | Computed from attachments |
| `total_paid_amount` | Portal sync |
| `converted` | Set by conversion flows |
| `merged_into_lead_id` | Set by merge action |
| `mobile_no` | Telecaller role cannot change |
| `hub_fee` | Immutable after first non-blank save |
| SLA fields | Managed by SLA engine |

---

## Validation on save

| Rule | Behaviour |
|---|---|
| Primary status transition lock | Telecaller/OA blocked from certain downgrades |
| Telecaller paid-lead lock | Cannot edit leads in paid/converted states |
| Telecaller mobile lock | Cannot change `mobile_no` |
| Unique identity docs | Duplicate `aadhar_no`, `pancard_number`, `driving_license_number` rejected |
| Location link | Must be valid URL |
| Primary lead | Vendor/secondary link validation |
| Status sync | `status` Link auto-resolved from primary + secondary |

---

## Preferred alternatives for complex updates

| Use case | API |
|---|---|
| Walk-in submission | `crm.api.lead.take_lead_actions` with `mark_walk_in_done` — [methods.md](methods.md) |
| Take Action (merge, drop, etc.) | `crm.api.lead.take_lead_actions` |
| Gate ticket / IN_HUB | `crm.api.lead.update_lead` |
| Optimistic locking bulk patch | `crm.api.update_doc.update_doc` |
| User tags | `crm.api.lead.apply_lead_user_tag` |

---

## Alternative — `frappe.client.set_value`

Update one or more fields without sending full doc:

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/frappe.client.set_value' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "doctype": "CRM Lead",
    "name": "AAAA0001",
    "fieldname": {
      "lead_name": "Updated Name",
      "last_remarks": "Follow-up done"
    }
  }'
```

---

## Related

- [GET — read](get.md)
- [POST — create](post.md)
- [DELETE](delete.md)
- [Method APIs](methods.md)
