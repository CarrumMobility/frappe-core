# CRM Lead — GET

**Route:** `GET /api/resource/CRM%20Lead`  
**See also:** [Resource API overview](../api.md) · [CRM Lead README](README.md)

---

## GET single document

Fetch one lead by display ID (`name`).

### Request

```
GET /api/resource/CRM%20Lead/{name}
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Lead display ID (e.g. `AAAA0001`) |

### curl

```bash
curl -b cookies.txt \
  'https://<your-site>/api/resource/CRM%20Lead/AAAA0001'
```

With API key:

```bash
curl 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Authorization: token <api_key>:<api_secret>'
```

### Response

Returns the full document dict with field-level read permissions applied. Sensitive fields the user cannot read are omitted.

```json
{
  "data": {
    "name": "AAAA0001",
    "doctype": "CRM Lead",
    "lead_name": "John Doe",
    "mobile_no": "9876543210",
    "mask_mobile_no": "**76543210",
    "lead_type": "LEAD",
    "primary_status": "New",
    "secondary_status": "New",
    "status": "<crm_lead_status.name>",
    "hub_visit_status": "NOT_IN_HUB",
    "source": "Website",
    "modified": "2026-07-14 10:00:00.000000"
  }
}
```

### Errors

| HTTP | Cause |
|---|---|
| `403` | No read permission on `CRM Lead` |
| `404` | Lead not found |

---

## GET list documents

Query multiple leads with filters, field selection, sorting, and pagination.

### Request

```
GET /api/resource/CRM%20Lead
```

### Query parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fields` | JSON array | `["name"]` | Columns to return |
| `filters` | JSON array | — | AND filter tuples |
| `or_filters` | JSON array | — | OR filter tuples |
| `order_by` | string | `modified desc` | Sort expression |
| `limit_start` | int | `0` | Offset |
| `limit_page_length` | int | `20` | Page size (`0` = unlimited) |

Filter format: `[["fieldname", "operator", "value"], ...]`

Common operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `like`, `in`, `not in`, `is`, `between`.

### curl — hub visit list

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'fields=["name","lead_name","mobile_no","primary_status","secondary_status","lead_type","hub_visit_status","gate_ticket_no"]' \
  --data-urlencode 'filters=[["lead_type","=","LEAD"],["hub_visit_status","=","IN_HUB"]]' \
  --data-urlencode 'order_by=modified desc' \
  --data-urlencode 'limit_start=0' \
  --data-urlencode 'limit_page_length=50'
```

### curl — search by mobile

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'filters=[["mobile_no","=","9876543210"]]' \
  --data-urlencode 'fields=["name","lead_name","mobile_no","status","primary_status","secondary_status"]'
```

### curl — search by lead name (partial)

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'filters=[["lead_name","like","%John%"]]' \
  --data-urlencode 'fields=["name","lead_name","mobile_no"]' \
  --data-urlencode 'limit_page_length=10'
```

### curl — drivers in a hub

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'filters=[["lead_type","=","DRIVER"],["hub_id","=","<hub-uuid>"]]' \
  --data-urlencode 'fields=["name","lead_name","mobile_no","custom_account_id","primary_status"]'
```

### curl — multiple lead IDs

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'filters=[["name","in",["AAAA0001","AAAA0002","AAAA0003"]]]' \
  --data-urlencode 'fields=["name","lead_name","mobile_no"]'
```

### Response

```json
{
  "data": [
    {
      "name": "AAAA0001",
      "lead_name": "John Doe",
      "mobile_no": "9876543210",
      "hub_visit_status": "IN_HUB"
    }
  ]
}
```

---

## GET count

Count matching documents without fetching rows.

### Request

```
GET /api/method/frappe.client.get_count?doctype=CRM Lead&filters=...
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doctype` | string | Yes | `CRM Lead` |
| `filters` | JSON array | No | Same filter format as list |

### curl

```bash
curl -b cookies.txt -G 'https://<your-site>/api/method/frappe.client.get_count' \
  --data-urlencode 'doctype=CRM Lead' \
  --data-urlencode 'filters=[["lead_type","=","DRIVER"]]'
```

**Response:** `{"message": 42}`

---

## Useful filter fields

| Field | Example use |
|---|---|
| `name` | Exact lead ID |
| `mobile_no` | Exact 10-digit mobile |
| `lead_type` | `LEAD`, `DRIVER`, `VENDOR` |
| `primary_status` / `secondary_status` | Disposition bucket |
| `status` | CRM Lead Status link PK |
| `hub_visit_status` | `NOT_IN_HUB`, `IN_HUB`, `HUB_VISITED` |
| `hub_id` | Carrum hub UUID |
| `telecaller` | Frappe username |
| `custom_account_id` | Portal account ID |
| `source` / `source_id` | Lead source |
| `modified` / `creation` | Date range filters |

Full field list: [fields.md](fields.md).

---

## Alternative — method API get

```bash
curl -b cookies.txt -G 'https://<your-site>/api/method/frappe.client.get' \
  --data-urlencode 'doctype=CRM Lead' \
  --data-urlencode 'name=AAAA0001'
```

```bash
curl -b cookies.txt -G 'https://<your-site>/api/method/frappe.client.get_list' \
  --data-urlencode 'doctype=CRM Lead' \
  --data-urlencode 'fields=["name","lead_name"]' \
  --data-urlencode 'filters=[["lead_type","=","LEAD"]]' \
  --data-urlencode 'limit_page_length=20'
```

---

## Related

- [POST — create](post.md)
- [PUT — update](put.md)
- [Method APIs — get_lead_action_list, etc.](methods.md)
