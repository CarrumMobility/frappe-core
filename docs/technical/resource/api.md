# Frappe REST Resource API

**Route prefix:** `/api/resource`  
**Implementation:** `frappe.client` (`apps/frappe/frappe/client.py`)  
**Status:** Live

---

## Overview

Carrum CRM exposes DocTypes through Frappe's standard REST resource layer. Any whitelisted DocType with read/write permissions can be queried and mutated at:

```
https://<your-site>/api/resource/<DocType>[/<name>]
```

DocType names containing spaces must be **URL-encoded** (e.g. `CRM Lead` → `CRM%20Lead`, `Lead walkin done` → `Lead%20walkin%20done`).

### Documented resources


| DocType            | Overview                                                 |
| ------------------ | -------------------------------------------------------- |
| `CRM Lead`         | [crm_lead/README.md](crm_lead/README.md)                 |
| `Lead walkin done` | [lead_walkin_done/README.md](lead_walkin_done/README.md) |


Business logic that goes beyond plain CRUD (walk-in submit, gate webhooks, duplicate checks) lives in **method APIs** at `/api/method/...` — see each DocType's `methods.md` or [CRM Lead methods](crm_lead/methods.md).

---



## Authentication


| Mechanism      | Header / cookie                               | Use case                                                    |
| -------------- | --------------------------------------------- | ----------------------------------------------------------- |
| Session cookie | `Cookie: sid=...`                             | Browser / SPA after login                                   |
| API key        | `Authorization: token <api_key>:<api_secret>` | Server-to-server integrations                               |
| CSRF token     | `X-Frappe-CSRF-Token: <token>`                | Required on **POST**, **PUT**, **DELETE** with session auth |
| Site name      | `X-Frappe-Site-Name: <hostname>`              | Multi-site benches                                          |




### Login (session)

```bash
curl -c cookies.txt -X POST 'https://<your-site>/api/method/login' \
  -H 'Content-Type: application/json' \
  -d '{"usr":"agent@example.com","pwd":"<password>"}'
```

Use the session cookie on subsequent requests. Pass `X-Frappe-CSRF-Token` from the login page or desk bootstrap on mutating calls.

### API key (server-to-server)

```bash
curl 'https://<your-site>/api/resource/CRM%20Lead/AAAA0001' \
  -H 'Authorization: token <api_key>:<api_secret>'
```

---



## HTTP routes


| Method   | Path                             | Action                                |
| -------- | -------------------------------- | ------------------------------------- |
| `GET`    | `/api/resource/{doctype}`        | List documents                        |
| `GET`    | `/api/resource/{doctype}/{name}` | Get single document                   |
| `POST`   | `/api/resource/{doctype}`        | Create document                       |
| `PUT`    | `/api/resource/{doctype}/{name}` | Update document (partial body merged) |
| `DELETE` | `/api/resource/{doctype}/{name}` | Delete document                       |


Equivalent whitelisted methods (same behaviour):


| REST      | Method API                                 |
| --------- | ------------------------------------------ |
| List      | `GET /api/method/frappe.client.get_list`   |
| Get       | `GET /api/method/frappe.client.get`        |
| Count     | `GET /api/method/frappe.client.get_count`  |
| Insert    | `POST /api/method/frappe.client.insert`    |
| Save      | `POST /api/method/frappe.client.save`      |
| Set value | `POST /api/method/frappe.client.set_value` |
| Delete    | `POST /api/method/frappe.client.delete`    |


---



## Common query parameters (GET list)

Passed as query string; JSON values are URL-encoded.


| Parameter           | Type       | Default         | Description                                             |
| ------------------- | ---------- | --------------- | ------------------------------------------------------- |
| `fields`            | JSON array | `["name"]`      | Columns to return. `["*"]` returns all permitted fields |
| `filters`           | JSON array | —               | AND filters: `[["field","operator","value"], ...]`      |
| `or_filters`        | JSON array | —               | OR filters (combined with AND filters)                  |
| `order_by`          | string     | `modified desc` | Sort field and direction                                |
| `limit_start`       | int        | `0`             | Pagination offset                                       |
| `limit_page_length` | int        | `20`            | Page size (`0` = no limit)                              |
| `as_dict`           | bool       | `true`          | Return objects instead of arrays                        |




### Filter operators


| Operator             | Example                                                |
| -------------------- | ------------------------------------------------------ |
| `=`                  | `[["lead_type","=","LEAD"]]`                           |
| `!=`                 | `[["primary_status","!=","Drop"]]`                     |
| `>`, `<`, `>=`, `<=` | `[["modified",">","2026-01-01"]]`                      |
| `like`               | `[["lead_name","like","%John%"]]`                      |
| `in`                 | `[["name","in",["AAAA0001","AAAA0002"]]]`              |
| `not in`             | `[["hub_visit_status","not in",["NOT_IN_HUB"]]]`       |
| `is`                 | `[["email","is","not set"]]`                           |
| `between`            | `[["creation","between",["2026-01-01","2026-12-31"]]]` |




### List example

```bash
curl -b cookies.txt -G 'https://<your-site>/api/resource/CRM%20Lead' \
  --data-urlencode 'fields=["name","lead_name","mobile_no"]' \
  --data-urlencode 'filters=[["lead_type","=","LEAD"]]' \
  --data-urlencode 'order_by=modified desc' \
  --data-urlencode 'limit_page_length=20'
```



### Count example

```bash
curl -b cookies.txt -G 'https://<your-site>/api/method/frappe.client.get_count' \
  --data-urlencode 'doctype=CRM Lead' \
  --data-urlencode 'filters=[["lead_type","=","DRIVER"]]'
```

---



## Request / response format



### Success — single document

```json
{
  "data": {
    "name": "AAAA0001",
    "doctype": "CRM Lead",
    "lead_name": "John Doe",
    "mobile_no": "9876543210",
    ...
  }
}
```

Some clients unwrap `data` automatically; raw Frappe responses may place the document under `data` or `message` depending on the route.

### Success — list

```json
{
  "data": [
    {"name": "AAAA0001", "lead_name": "John Doe"},
    {"name": "AAAA0002", "lead_name": "Jane Doe"}
  ]
}
```



### Error

```json
{
  "exc_type": "ValidationError",
  "_server_messages": "[\"{\\\"message\\\": \\\"Mobile No is required\\\", ...}\"]",
  "_error_message": "Mobile No is required"
}
```

HTTP status codes: `403` permission denied, `404` not found, `417` validation / business rule failure, `500` server error.

---



## POST / PUT body

Send a JSON object whose keys are DocType field names. Standard metadata fields are managed by the server:


| Field                                          | Set by                                  |
| ---------------------------------------------- | --------------------------------------- |
| `name`                                         | Autoname / naming series (on insert)    |
| `owner`, `creation`, `modified`, `modified_by` | Server                                  |
| `docstatus`                                    | Submit/cancel workflows (if applicable) |


**PUT** loads the existing document, merges the supplied keys, runs validations, and saves. Omitted fields are unchanged.

**POST** creates a new row; required fields depend on the DocType schema.

---



## Permissions

Every request checks Frappe DocType permissions for the session user:

1. **Role permissions** — from DocType JSON (`read`, `write`, `create`, `delete`)
2. **Custom permissions** — `role_perm_service` grants CRM agent roles at runtime
3. **List scoping** — `crm.api.doc` applies hub/role filters on CRM Lead list views (desk UI; raw REST list still respects DocType read permission)

Field-level read permissions strip restricted columns from GET responses.

---



## Best practices

1. **URL-encode DocType names** with spaces.
2. **Prefer method APIs** when business rules apply (`create_lead`, `take_lead_actions`) instead of raw POST when duplicates or defaults matter.
3. **Use partial PUT** for updates — only send changed fields.
4. **Paginate list calls** — default page size is 20.
5. **Handle optimistic conflicts** — if using `crm.api.update_doc`, refresh on conflict errors.

---



## Related documentation

- [CRM Lead](crm_lead/README.md)
- [Lead walkin done](lead_walkin_done/README.md)
- [Walk-in Form](../walkin_form.md)

