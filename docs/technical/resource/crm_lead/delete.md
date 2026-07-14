# CRM Lead — DELETE

**Route:** `DELETE /api/resource/CRM%20Lead/{name}`  
**See also:** [Resource API overview](../api.md) · [CRM Lead README](README.md)

---

## Delete document

Permanently remove a CRM Lead row.

> **Warning:** Deleting a lead removes the record from the database. Linked `Lead walkin done` rows, events, and call logs may become orphaned or blocked by link constraints depending on site configuration. Prefer status changes (Drop) over deletion in production.

### Request

```
DELETE /api/resource/CRM%20Lead/{name}
X-Frappe-CSRF-Token: <csrf_token>
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Lead display ID (e.g. `AAAA0001`) |

### curl

```bash
curl -b cookies.txt -X DELETE 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>'
```

With API key:

```bash
curl -X DELETE 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Authorization: token <api_key>:<api_secret>'
```

### Response

Empty body or confirmation message on success.

```json
{
  "message": "ok"
}
```

### Errors

| HTTP / error | Cause |
|---|---|
| `403` | No delete permission on `CRM Lead` |
| `404` | Lead not found |
| `LinkExistsError` | Another document links to this lead |

---

## Permissions

Delete requires the **delete** permission on `CRM Lead`. DocType JSON grants delete to:

- System Manager
- Sales Manager
- Sales User

CRM agent roles may have delete restricted at runtime via custom permission rules.

---

## Alternative — method API

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/frappe.client.delete' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "doctype": "CRM Lead",
    "name": "AAAA0001"
  }'
```

---

## Related

- [GET — read](get.md)
- [POST — create](post.md)
- [PUT — update](put.md)
