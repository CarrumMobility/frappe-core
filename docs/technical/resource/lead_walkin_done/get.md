# Lead walkin done — GET

**Route:** `GET /api/resource/Lead%20walkin%20done`  
**See also:** [README](README.md) · [Resource API overview](../api.md)

---

## GET single document

```
GET /api/resource/Lead%20walkin%20done/{name}
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Walk-in record ID (hash) |

### curl

```bash
curl -b cookies.txt \
  'https://<your-site>/api/resource/Lead%20walkin%20done/a1b2c3d4e5'
```

### Response

```json
{
  "data": {
    "name": "a1b2c3d4e5",
    "doctype": "Lead walkin done",
    "lead": "AAAA0001",
    "source": "Google",
    "primary_status": "Interested",
    "secondary_status": "Walk-in Done",
    "lead_status_link": "<crm_lead_status.name>",
    "remarks": "Interested in Black rental",
    "business_type": "Black",
    "callback_at": null,
    "callback_type": null,
    "telecaller": null,
    "referrer_name": null,
    "referrer_mobile_no": null,
    "referrer_user_link": null,
    "created_by": "onboarding@example.com",
    "walkin_form_filled_at": "2026-07-14 11:30:00",
    "creation": "2026-07-14 11:30:00",
    "modified": "2026-07-14 11:30:00"
  }
}
```

---

## GET list documents

```
GET /api/resource/Lead%20walkin%20done
```

### Query parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fields` | JSON array | `["name"]` | Columns to return |
| `filters` | JSON array | — | Filter tuples |
| `order_by` | string | `modified desc` | Sort |
| `limit_start` | int | `0` | Offset |
| `limit_page_length` | int | `20` | Page size |

### curl — all walk-ins for a lead

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/Lead%20walkin%20done' \
  --data-urlencode 'filters=[["lead","=","AAAA0001"]]' \
  --data-urlencode 'fields=["name","lead","source","primary_status","secondary_status","remarks","walkin_form_filled_at","created_by"]' \
  --data-urlencode 'order_by=creation desc'
```

### curl — walk-ins by source

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/Lead%20walkin%20done' \
  --data-urlencode 'filters=[["source","=","referrals"]]' \
  --data-urlencode 'fields=["name","lead","source","referrer_name","referrer_mobile_no","creation"]' \
  --data-urlencode 'limit_page_length=50'
```

### curl — walk-ins with callbacks scheduled

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/Lead%20walkin%20done' \
  --data-urlencode 'filters=[["callback_type","=","Callback"],["callback_at","is","set"]]' \
  --data-urlencode 'fields=["name","lead","callback_at","remarks","primary_status"]'
```

### curl — walk-ins submitted by agent

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/Lead%20walkin%20done' \
  --data-urlencode 'filters=[["created_by","=","onboarding@example.com"]]' \
  --data-urlencode 'filters=[["creation","between",["2026-07-01","2026-07-31"]]]' \
  --data-urlencode 'fields=["name","lead","source","primary_status","creation"]'
```

---

## GET count

```bash
curl -b cookies.txt -G 'https://<your-site>/api/method/frappe.client.get_count' \
  --data-urlencode 'doctype=Lead walkin done' \
  --data-urlencode 'filters=[["lead","=","AAAA0001"]]'
```

---

## Resolve latest walk-in from CRM Lead

The parent lead stores a pointer to the most recent submission:

```bash
curl -b cookies.txt \
  'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  | jq '.data.walkin_form_link'
```

Then fetch that record:

```bash
curl -b cookies.txt \
  'https://<your-site>/api/resource/Lead%20walkin%20done/<walkin_form_link>'
```

Or use `total_walkin_forms_filled` on the lead to see repeat-visit count.

---

## Useful filter fields

| Field | Example |
|---|---|
| `lead` | All walk-ins for lead `AAAA0001` |
| `source` | Filter by source label |
| `primary_status` / `secondary_status` | Disposition snapshot |
| `lead_status_link` | Specific CRM Lead Status row |
| `created_by` | Submitting agent |
| `telecaller` | Telecaller attribution |
| `callback_type` | `Callback` or `Visit Date` |
| `creation` / `walkin_form_filled_at` | Date range |

---

## Related

- [POST — create](post.md)
- [CRM Lead GET — walkin_form_link](../crm_lead/get.md)
- [take_lead_actions](../crm_lead/methods.md#take_lead_actions)
