# Lead walkin done — PUT

**Route:** `PUT /api/resource/Lead%20walkin%20done/{name}`  
**See also:** [README](README.md) · [fields.md](fields.md)

---

## Update document (partial)

Update an existing walk-in audit record. Walk-in records are primarily **immutable audit snapshots** — updates should be rare and limited to corrections.

### Request

```
PUT /api/resource/Lead%20walkin%20done/{name}
Content-Type: application/json
X-Frappe-CSRF-Token: <csrf_token>
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Walk-in record ID |

### Updatable fields

| Field | Notes |
|---|---|
| `remarks` | Correct agent comment |
| `callback_at` | Adjust scheduled datetime |
| `callback_type` | `Callback` or `Visit Date` |
| `business_type` | Product correction |
| `referrer_name` / `referrer_mobile_no` / `referrer_user_link` | Referral corrections |
| `telecaller` | Telecaller attribution fix |

> Changing `lead`, `lead_status_link`, or status snapshots after submission is discouraged — prefer creating a new walk-in via `take_lead_actions`.

### curl — update remarks

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/Lead%20walkin%20done/f6g7h8i9j0' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "remarks": "Corrected: interested in Go scheme, not Black"
  }'
```

### curl — update callback datetime

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/Lead%20walkin%20done/f6g7h8i9j0' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "callback_at": "2026-07-16 14:00:00",
    "callback_type": "Callback"
  }'
```

### Response

Returns updated document dict.

### Errors

| Error | Cause |
|---|---|
| `403` | No write permission |
| `404` | Record not found |

---

## Note on parent lead consistency

Updating a `Lead walkin done` record does **not** automatically sync changes back to the parent `CRM Lead` or related `Event` rows. If disposition changed materially, submit a new walk-in form via `take_lead_actions` instead.

---

## Alternative — `frappe.client.set_value`

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/frappe.client.set_value' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "doctype": "Lead walkin done",
    "name": "f6g7h8i9j0",
    "fieldname": "remarks",
    "value": "Updated remark"
  }'
```

---

## Related

- [GET](get.md) · [POST](post.md) · [DELETE](delete.md)
