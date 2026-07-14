# Lead walkin done — DELETE

**Route:** `DELETE /api/resource/Lead%20walkin%20done/{name}`  
**See also:** [README](README.md)

---

## Delete document

Remove a walk-in audit record.

> **Warning:** Deleting walk-in records breaks audit history. The parent `CRM Lead` may still reference the deleted row via `walkin_form_link`. Prefer retaining records for compliance and agent performance metrics.

### Request

```
DELETE /api/resource/Lead%20walkin%20done/{name}
X-Frappe-CSRF-Token: <csrf_token>
```

| Path parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Walk-in record ID |

### curl

```bash
curl -b cookies.txt -X DELETE 'https://<your-site>/api/resource/Lead%20walkin%20done/f6g7h8i9j0' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>'
```

### Response

Empty body or `{"message": "ok"}` on success.

### Errors

| HTTP | Cause |
|---|---|
| `403` | No delete permission |
| `404` | Record not found |

---

## After deletion

If the deleted record was pointed to by `CRM Lead.walkin_form_link`, clear or repoint that field on the parent lead:

```bash
curl -b cookies.txt -X PUT 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{"walkin_form_link": null, "walkin_form_filled_at": null}'
```

Or query the latest remaining walk-in for the lead and update the pointer.

---

## Alternative — method API

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/frappe.client.delete' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{
    "doctype": "Lead walkin done",
    "name": "f6g7h8i9j0"
  }'
```

---

## Permissions

Delete requires **delete** permission. DocType JSON grants delete to System Manager only; CRM agent roles typically have create/read/write but not delete at runtime.

---

## Related

- [GET](get.md) · [POST](post.md) · [PUT](put.md)
- [CRM Lead DELETE](../crm_lead/delete.md)
