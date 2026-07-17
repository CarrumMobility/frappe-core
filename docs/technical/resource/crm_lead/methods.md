# CRM Lead — Method APIs

**Base path:** `/api/method/`  
**Module:** `crm.api.lead`, `core.api.carrum_drivers`  
**See also:** [README](README.md) · [REST routes](get.md)

Method APIs encapsulate business rules beyond plain REST CRUD. Use these when duplicates, defaults, webhooks, or Take Action flows apply.

---

## `crm.api.lead`

### `create_lead`

Create a lead (referral / quick entry). **GET or POST.**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lead_name` | string | Yes* | *Or alias `name` |
| `name` | string | No | Alias for `lead_name` |
| `mobile_no` | string | Yes | Normalized to 10-digit Indian |
| `salutation` | string | No | |
| `email` | string | No | |
| `source` | string | No | Source label |
| `source_id` | string | No | `CRM Lead Source.name` |
| `status` | string | No | Default status if omitted |
| `telecaller` | string | No | Only if caller has Telecaller role |
| `no_of_employees` | string | No | |
| `primary_lead` | string | No | Link to primary lead |
| `lead_type` | string | No | `LEAD` \| `DRIVER` \| `VENDOR` |
| `extra_fields` | JSON | No | Reserved |

**Duplicate error:** `CRM_DUPLICATE_LEAD|Lead|AAAA0001` or `...|DRIVER|...|RAISE_DRIVER_RETURN`

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.create_lead' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{"lead_name":"Jane Doe","mobile_no":"9876543210","status":"<status_pk>"}'
```

---

### `create_vendor_lead`

**POST only.**

| Parameter | Type | Required |
|---|---|---|
| `phoneNumber` | string | Yes |
| `name` | string | No |
| `bank_account_number` | string | No |
| `bank_ifsc` | string | No |
| `referral_scheme_id` | string | Yes |
| `hub_name` | string | Yes |
| `hub_id` | string | Yes |

---

### `get_next_lead_id`

Returns next Redis sequence ID (peek; consumed on insert).

```bash
curl -b cookies.txt 'https://<your-site>/api/method/crm.api.lead.get_next_lead_id'
```

---

### `update_lead_id_sequence_API`

Admin: advance Redis counter.

| Parameter | Type | Required |
|---|---|---|
| `next_lead_id` | string | Yes |

---

### `update_lead` (Gate App)

**POST.** JSON body.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `phoneNo` | string | Yes | Visitor mobile |
| `ticketNo` | string | No | → `gate_ticket_no` |
| `createdAt` | datetime | No | → `custom_gate_ticket_generated_at` |
| `hubId` | string | No | → `hub_id` |
| `hubName` | string | No | → `custom_hub_name` |
| `category` | string | No | → `hubvisit_category` |
| `subCategory` | string | No | → `hubvisit_subcategory` |

Sets `hub_visit_status = IN_HUB`. Clears `walkin_form_filled_at` and `walkin_form_link` on existing leads.

---

### `convert_lead_to_driver`

**POST.** JSON body.

| Parameter | Type | Required |
|---|---|---|
| `driverCarrumId` | string | Yes |
| `driverPhone` | string | Yes |
| `driverHubId` | string | No |
| `driverHubName` | string | No |
| `driverUserId` | string | No |
| `driverName` | string | No |
| `driverEmail` | string | No |

---

### `get_lead_action_list`

**POST.**

| Parameter | Type | Required |
|---|---|---|
| `lead_id` | string | Yes |

Returns `actions[]` and Take Action modal `config`.

**Action slugs:** `mark_walk_in_done`, `mark_onboarding_drop`, `remove_onboarding_drop`, `merge_lead`, `unmerge_lead`, `raise_driver_reactivation_request`

---

### `take_lead_actions`

**POST.** Executes a Take Action.

| Parameter | Type | Required |
|---|---|---|
| `lead_id` | string | Yes |
| `action` | string | Yes |
| *(action-specific)* | various | varies |

#### `mark_walk_in_done`

| Parameter | Type | Required |
|---|---|---|
| `lead_status` | string | Yes |
| `source` | string | Yes |
| `source_pk` | string | No |
| `remarks` | string | Conditional |
| `lead_name` | string | Conditional |
| `business_type` | string | Yes (UI) |
| `callback_datetime` | datetime | Conditional |
| `scheduled_visit_date` | datetime | Conditional |
| `callback_type` | string | No |
| `telecaller` | string | Conditional |
| `hub_id` / `hub_name` | string | No |
| `referrer_name` / `referrer_mobile_no` / `referrer_user_link` | string | No |
| `remind_before_minutes` | int | No |
| `expected_call_duration_minutes` | int | No |

Creates [Lead walkin done](../lead_walkin_done/README.md) record. See [Walk-in Form](../../walkin_form.md).

```bash
curl -b cookies.txt -X POST 'https://<your-site>/api/method/crm.api.lead.take_lead_actions' \
  -H 'Content-Type: application/json' \
  -H 'X-Frappe-CSRF-Token: <csrf_token>' \
  -d '{"lead_id":"AAAA0001","action":"mark_walk_in_done","source":"Walk In","lead_status":"<pk>","remarks":"Interested"}'
```

#### Other actions

| Action | Key parameters |
|---|---|
| `merge_lead` | `merged_into_lead_id` |
| `mark_onboarding_drop` | `lead_status_pk` |
| `unmerge_lead` | — |
| `remove_onboarding_drop` | — |
| `raise_driver_reactivation_request` | `remarks`, `identification_key`, `identification_value`, `new_account_id` |

---

### Walk-in & telecaller helpers

| Method | HTTP | Description |
|---|---|---|
| `get_walkin_form_status` | GET/POST | Onboarding status rows |
| `get_telecaller_support_dispositions` | GET/POST | Telecaller dispose statuses |
| `get_telecaller_user_options` | GET/POST | Hub telecaller dropdown |
| `get_possible_onboarding_drop_statuses` | GET/POST | Onboarding drop statuses |

---

### Tags

| Method | Parameters |
|---|---|
| `apply_lead_user_tag` | `lead_id`, `color`, `label`, `remove` |
| `get_core_tags` | — |

---

### Vehicle & payment

| Method | Key parameters |
|---|---|
| `lead_vehicle_auto_assign` | `lead_id`, `vendor_count_details` |
| `lead_vehicle_update_requested` | `lead_id`, `requested_cars_list` |
| `lead_vehicle_cancel_request` | `request_id` |
| `assign_dm` | `custom_account_id`, `dmId` |
| `get_emis` | `scheme_car_type_id` |
| `submit_cheque` | `lead_id`, `bank_account_number`, `cheque_image` |
| `get_employee_agent_options` | — |
| `get_dm_of_all_businessTypes` | `leadId` |

---

### Webhooks & utilities

| Method | Auth | Description |
|---|---|---|
| `scheme_change_webhook` | Guest POST | Portal scheme change |
| `redirect_to_lead_detail` | Guest GET | `?phone=` → redirect to lead |
| `crm_lead_link_search_query` | Session | Link field search |

---

## `core.api.carrum_drivers`

| Method | Description |
|---|---|
| `lead_creation_webhook` | POST — create or update from portal (`phoneNo`, optional `source`) |
| `driver_status_update_webhook` | POST — `accountId`, `newStatus` |
| `get_portal_driver_detail` | `name`, optional `sync` |
| `update_driver` | `account_id`, `data` (scheme/EMI) |

### `lead_creation_webhook`

POST webhook from the Carrum portal.

**Body:** `mobile_no` / `phoneNo` / `phone` (required), optional `source` (`uber` or `website`, case-insensitive).

**Behavior:**

| Case | Action |
|---|---|
| Lead exists for normalized phone | Updates `source` and `source_id` when source resolves; returns `created: false` |
| No matching lead | Creates a new CRM Lead; when source resolves, also sets `upload_source` and `lead_uploaded_at` |

**Response:** `{ "message": "ok", "name": "<lead_id>", "created": true \| false }`

```bash
curl -X POST 'https://<your-site>/api/method/core.api.carrum_drivers.lead_creation_webhook' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: token <api_key>:<api_secret>' \
  -d '{"phoneNo":"9876543210","source":"uber"}'
```

---

## Related

- [REST GET](get.md) · [POST](post.md) · [PUT](put.md) · [DELETE](delete.md)
- [Lead walkin done methods](../lead_walkin_done/README.md) — audit records created by walk-in submit
