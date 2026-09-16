# CARRUM CRM APIs

Integration API reference for Carrum CRM.


| Env  | Base URL                       |
| ---- | ------------------------------ |
| DEV  | `https://erp-dev.carrum.co.in` |
| PROD | `https://erp.carrum.co.in`     |


In examples below:


| Placeholder   | Meaning                  |
| ------------- | ------------------------ |
| `<<baseUrl>>` | Carrum crm base url      |
| `<<token>>`   | `backend provided token` |


Unless noted otherwise, method APIs return a Frappe envelope:

```json
{
  "message": { }
}
```

The tables below describe the **inner** `message` payload (or the resource `data` object for `/api/resource`).

---



## Authentication

API-key auth (server-to-server). The system issues a fixed key pair.


| Header          | Type     | Required | Description                                                           |
| --------------- | -------- | -------- | --------------------------------------------------------------------- |
| `Authorization` | `string` | Yes      | `<<token>>` → `token <api_key>:<api_secret>`                          |
| `Content-Type`  | `string` | Yes*     | `application/json` for JSON bodies; `multipart/form-data` for uploads |
| `Accept`        | `string` | No       | `application/json`                                                    |


```bash
curl --location 'https://<<baseUrl>>/api/resource/CRM%20Lead/AAAA0001' \
  --header 'Authorization: <<token>>'
```

> Session cookie + CSRF is used by the CRM SPA; integrations should use API key auth.

---



## Common API error response

Failed requests return a Frappe error envelope (HTTP `401` / `403` / `404` / `417` / `500` depending on the failure). Shape is the same for `/api/resource/...` and `/api/method/...`.


| Key                | Type     | Description                                                                             |
| ------------------ | -------- | --------------------------------------------------------------------------------------- |
| `exception`        | `string` | Fully qualified exception class (e.g. `frappe.exceptions.AuthenticationError`)          |
| `exc_type`         | `string` | Short exception name (e.g. `AuthenticationError`, `ValidationError`, `PermissionError`) |
| `exc`              | `string` | JSON-encoded array of traceback string(s)                                               |
| `session_expired`  | `number` | Present on auth failures; `1` means credentials/session are invalid                     |
| `_server_messages` | `string` | Optional; JSON-encoded list of server message objects (validation / business errors)    |
| `_error_message`   | `string` | Optional; short human-readable error when available                                     |




### Example — authentication failure

HTTP status: `401`

```json
{
  "session_expired": 1,
  "exception": "frappe.exceptions.AuthenticationError",
  "exc_type": "AuthenticationError",
  "exc": "[\"Traceback (most recent call last):\\n  File \\\"apps/frappe/frappe/app.py\\\", line 144, in application\\n    validate_auth()\\n  File \\\"apps/frappe/frappe/auth.py\\\", line 625, in validate_auth\\n    validate_auth_via_api_keys(authorization_header)\\n  File \\\"apps/frappe/frappe/auth.py\\\", line 698, in validate_auth_via_api_keys\\n    validate_api_key_secret(api_key, api_secret, authorization_source)\\n  File \\\"apps/frappe/frappe/auth.py\\\", line 722, in validate_api_key_secret\\n    raise frappe.AuthenticationError\\nfrappe.exceptions.AuthenticationError\\n\"]"
}
```

Typical causes: missing `Authorization` header, wrong `api_key` / `api_secret`, or revoked key.

### Example — validation / business rule failure

HTTP status: often `417`

```json
{
  "exception": "frappe.exceptions.ValidationError",
  "exc_type": "ValidationError",
  "exc": "[\"...\"]",
  "_server_messages": "[\"{\\\"message\\\": \\\"Mobile No is required\\\", ...}\"]",
  "_error_message": "Mobile No is required"
}
```

Integrations should branch on `exc_type` (and `_error_message` / `_server_messages` when present), not on traceback text in `exc`.

---



## Lead — Find or Create

**Method:** `POST`
**Path:** `/api/method/core.api.lead.find_or_create_lead`
**Content-Type:** `application/json`

Finds an existing CRM Lead by mobile number or creates a new one. Idempotent — safe to call on every inbound driver entry.

### Body parameters


| Name            | Type     | Required | Description                                            |
| --------------- | -------- | -------- | ------------------------------------------------------ |
| `mobile_no`     | `string` | Yes      | Driver mobile number (used to find or create the lead) |
| `upload_source` | `string` | Yes      | Identifier of the uploading system / channel           |
| `name`          | `string` | No       | Driver full name (`lead_name`) — applied on create     |
| `source`        | `string` | No       | Lead source key                                        |
| `source_id`     | `string` | No       | External source reference ID                           |
| `hub_id`        | `string` | No       | Carrum hub ID                                          |
| `hub_name`      | `string` | No       | Carrum hub display name                                |




### Success response (`message`)


| Key    | Type     | Description                                     |
| ------ | -------- | ----------------------------------------------- |
| `lead` | `object` | Found or newly created CRM Lead document (dict) |


```bash
curl --location '<<baseUrl>>/api/method/core.api.lead.find_or_create_lead' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "mobile_no": "9876543210",
    "upload_source": "referral_portal",
    "name": "Ravi Kumar",
    "source": "referral",
    "source_id": "REF-001",
    "hub_id": "HUB-001",
    "hub_name": "Delhi Hub"
  }'
```

---



## Lead — Update

**Method:** `POST`
**Path:** `/api/method/core.api.lead.update_lead`
**Content-Type:** `application/json`

Updates fields on a CRM Lead. ERP fields are written to the database; portal fields are forwarded to the Carrum portal via `update_driver`. Both updates happen in the same call.

### Body parameters


| Name             | Type     | Required | Description                                                                                  |
| ---------------- | -------- | -------- | -------------------------------------------------------------------------------------------- |
| `lead_id`        | `string` | Yes      | CRM Lead name (e.g. `"AAAA0001"`)                                                            |
| `lead_updates`   | `object` | Yes      | Flat map of `fieldName → value` for ERP fields to write on the lead                          |
| `portal_updates` | `object` | No       | Flat map of Carrum portal fields to forward to `update_driver` (e.g. `scheme_id`, `uber_id`) |
| `lsq_id`         | `string` | No       | External LSQ reference (logging only)                                                        |


> Any valid CRM Lead field name can be used in `lead_updates`. There is no fixed allow-list — the field is set directly on the doc.



### Success response (`message`)


| Key                   | Type     | Description                                                  |
| --------------------- | -------- | ------------------------------------------------------------ |
| `is_valid`            | `bool`   | `true`                                                       |
| `data.lead`           | `object` | Updated CRM Lead document (dict) after save                  |
| `data.lead_updates`   | `object` | Echo of the `lead_updates` that were requested               |
| `data.portal_updates` | `object` | Echo of the `portal_updates` that were requested (or `null`) |


```bash
curl --location '<<baseUrl>>/api/method/core.api.lead.update_lead' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "lead_id": "AAAA0001",
    "lead_updates": {
      "mobile_no": "9876543210",
      "primary_status": "Active"
    },
    "portal_updates": {
      "scheme_id": 42
    }
  }'
```

---



## Lead — Get

**Method:** `GET`
**Path:** `/api/method/core.api.lead.get_lead`

Fetch a single CRM Lead document by its name. For driver-type leads also returns the latest Carrum portal driver detail.

### Query parameters


| Name      | Type     | Required | Description                           |
| --------- | -------- | -------- | ------------------------------------- |
| `lead_id` | `string` | Yes      | CRM Lead name (e.g. `"AAAA0001"`)     |
| `lsq_id`  | `string` | No       | External LSQ reference (logging only) |




### Success response (`message`)


| Key                   | Type     | Description              |
| --------------------- | -------- | ------------------------ |
| `is_valid`            | `bool`   | `true`                   |
| `data.lead_details`   | `object` | CRM Lead document (dict) |
| `data.portal_details` | `object  | null`                    |


```bash
curl --location '<<baseUrl>>/api/method/core.api.lead.get_lead?lead_id=AAAA0001' \
  --header 'Authorization: <<token>>'
```

---



## 1. Document upload (lead detail Attachments)

Uploads a file into attachments. To bind it to a specific lead field, call the lead update API with the returned `file_url` to mark the file.


|                  |                           |
| ---------------- | ------------------------- |
| **Method**       | `POST`                    |
| **Path**         | `/api/method/upload_file` |
| **Content-Type** | `multipart/form-data`     |




#### Form fields


| Key       | Type            | Required | Description        |
| --------- | --------------- | -------- | ------------------ |
| `file`    | `file` (binary) | Yes      | File bytes         |
| `doctype` | `string`        | Yes      | `"CRM Lead"`       |
| `docname` | `string`        | Yes      | Carrum CRM Lead Id |




#### Success response (`message`)


| Key          | Type                 | Description                   |
| ------------ | -------------------- | ----------------------------- |
| `name`       | `string`             | File document name            |
| `file_name`  | `string`             | Stored file name              |
| `file_url`   | `string`             | URL to use in later APIs      |
| `is_private` | `boolean` / `number` | Privacy flag                  |
| `file_size`  | `number`             | Size in bytes (when returned) |


```bash
curl --location '<<baseUrl>>/api/method/upload_file' \
  --header 'Authorization: <<token>>' \
  --form 'file=@"<<filePath>>"' \
  --form 'doctype="CRM Lead"' \
  --form 'docname="FACV3468"'
```

---



## 2. Generate payment link


|                  |                                                         |
| ---------------- | ------------------------------------------------------- |
| **Method**       | `POST`                                                  |
| **Path**         | `/api/method/core.api.carrum_payment.send_payment_link` |
| **Content-Type** | `application/json`                                      |




#### Request body


| Key              | Type     | Required | Description                                                                   |
| ---------------- | -------- | -------- | ----------------------------------------------------------------------------- |
| `lead_id`        | `string` | Yes      | Lead id                                                                       |
| `amount`         | `number` | Yes      | Must be `> 0`                                                                 |
| `tag_type`       | `string` | Yes      | `security_deposit`                                                            |
| `portal_user_id` | `string` | No       | Carrum portal user id; sent as `accountCreatorId`. Falls back to session user |




#### Success response (`message`)


| Key                 | Type     | Description        |
| ------------------- | -------- | ------------------ |
| `paymentLink`       | `string` | Payment URL        |
| `paymentQrCodeLink` | `string` | QR image / QR link |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_payment.send_payment_link' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "lead_id": "AAAA0001",
    "amount": 5000,
    "tag_type": "security_deposit",
    "portal_user_id": "portal-user-uuid"
  }'
```

---



## 3. Add other payment


|                  |                                                         |
| ---------------- | ------------------------------------------------------- |
| **Method**       | `POST`                                                  |
| **Path**         | `/api/method/core.api.carrum_payment.add_other_payment` |
| **Content-Type** | `application/json`                                      |




#### Request body


| Key              | Type            | Required | Description                                                                   |
| ---------------- | --------------- | -------- | ----------------------------------------------------------------------------- |
| `lead_id`        | `string`        | Yes      | Lead id                                                                       |
| `amount`         | `string`        | `number` | Cond.                                                                         |
| `utr`            | `string`        | Cond.    | Required if `amount` is empty                                                 |
| `payment_type`   | `string`        | Yes      | Normalized to `security_deposit` or `settlement`                              |
| `image_urls`     | `array<string>` | No       | Receipt / proof URLs from upload                                              |
| `image_url`      | `string`        | No       | Single URL alias                                                              |
| `portal_user_id` | `string`        | No       | Carrum portal user id; sent as `accountCreatorId`. Falls back to session user |




#### Success response (`message`)


| Key        | Type      | Description             |
| ---------- | --------- | ----------------------- |
| `is_valid` | `boolean` | `true` on success       |
| `reason`   | `string`  | `null`                  |
| `data`     | `object`  | Upstream Portal payload |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_payment.add_other_payment' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "lead_id": "AAAA0001",
    "amount": "5000",
    "utr": "UTR123456",
    "payment_type": "security_deposit",
    "image_urls": ["/files/receipt.pdf"],
    "portal_user_id": "portal-user-uuid"
  }'
```

---



## 4. Add cash payment


|                  |                                                |
| ---------------- | ---------------------------------------------- |
| **Method**       | `POST`                                         |
| **Path**         | `/api/method/core.api.carrum_payment.add_cash` |
| **Content-Type** | `application/json`                             |




#### Request body


| Key              | Type            | Required | Description           |
| ---------------- | --------------- | -------- | --------------------- |
| `leadId`         | `string`        | Yes      | Carrum CRM Lead Id    |
| `amount`         | `number`        | Yes      | Cash amount           |
| `paymentType`    | `string`        | Yes      | `security_deposit`    |
| `imageUrls`      | `array<string>` | No       | Receipt URLs          |
| `portal_user_id` | `string`        | No       | Carrum portal user id |




#### Success response (`message`)


| Key        | Type      | Description                 |
| ---------- | --------- | --------------------------- |
| `message`  | `string`  | `"success"` on success      |
| `is_valid` | `boolean` | Present on failure path     |
| `reason`   | `string`  | Failure reason when invalid |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_payment.add_cash' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "leadId": "AAAA0001",
    "amount": 5000,
    "paymentType": "security_deposit",
    "imageUrls": ["/files/receipt.pdf"],
    "portal_user_id": "portal-user-uuid"
  }'
```

---



## 5. Add cheque payment


|                  |                                          |
| ---------------- | ---------------------------------------- |
| **Method**       | `POST`                                   |
| **Path**         | `/api/method/crm.api.lead.submit_cheque` |
| **Content-Type** | `application/json`                       |


Upload the cheque image first via **Document upload**, then pass `file_url` as `cheque_image`. Checque can only be added for driver not Lead

#### Request body


| Key                   | Type     | Required | Description         |
| --------------------- | -------- | -------- | ------------------- |
| `lead_id`             | `string` | Yes      | Lead id             |
| `bank_account_number` | `string` | Yes      | Bank account number |
| `cheque_image`        | `string` | Yes      | Uploaded file URL   |
| `account_id`          | `string` | Cond.    | Carrum account UUID |




#### Success response (`message`)


| Key       | Type     | Description               |
| --------- | -------- | ------------------------- |
| `message` | `string` | e.g. `"Cheque submitted"` |
| `data`    | `object` | Upstream Carrum payload   |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.submit_cheque' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "lead_id": "AAAA0001",
    "bank_account_number": "1234567890",
    "cheque_image": "/files/cheque.jpg",
    "account_id": "account-uuid"
  }'
```

---



## 6. Agreement list


|            |                                                             |
| ---------- | ----------------------------------------------------------- |
| **Method** | `GET`                                                       |
| **Path**   | `/api/method/core.api.carrum_drivers.get_driver_agreements` |




#### Parameters (query)


| Key       | Type     | Required | Description |
| --------- | -------- | -------- | ----------- |
| `lead_id` | `string` | Yes      |             |




#### Success response (`message`)

Passthrough Carrum JSON:


| Key                        | Type            | Description              |
| -------------------------- | --------------- | ------------------------ |
| `results`                  | `object`        | Result container         |
| `results.agreementHistory` | `array<object>` | Agreement rows           |
| `results.driverDetails`    | `object`        | Optional driver metadata |


Agreement row fields commonly used:


| Key                | Type                | Description          |
| ------------------ | ------------------- | -------------------- |
| `id`               | `string`            | Agreement history id |
| `digio_id`         | `string`            | Digio id             |
| `driver_id`        | `string`            | Driver id            |
| `agreement_status` | `string`            | Status               |
| `sign_mode`        | `string`            | Signing mode         |
| `offline_pic`      | `string`            | Offline image URL    |
| `createdAt`        | `string` (datetime) | Created at           |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.get_driver_agreements?lead_id=FACV3458' \
  --header 'Authorization: <<token>>'
```

---



## 7. Mark agreement completed / failed


|                  |                                                                       |
| ---------------- | --------------------------------------------------------------------- |
| **Method**       | `POST`                                                                |
| **Path**         | `/api/method/core.api.carrum_drivers.update_agreement_history_status` |
| **Content-Type** | `application/json`                                                    |




#### Request body


| Key                | Type     | Required | Description               |
| ------------------ | -------- | -------- | ------------------------- |
| `agreement_id`     | `string` | Yes      | Agreement history id      |
| `leadId`           | `string` | Yes      | CRM Lead id               |
| `agreement_status` | `string` | Req      | Enum - completed / failed |




#### Success response (`message`)


| Key       | Type      | Description                                                                   |
| --------- | --------- | ----------------------------------------------------------------------------- |
| `success` | `boolean` | `true`                                                                        |
| `data`    | `object`  | Upstream Carrum response                                                      |
| `_debug`  | `object`  | Debug metadata (`url`, `payload`, `response`, `status_code`, `response_text`) |


```bash

curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.update_agreement_history_status' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "agreement_id": "agreement-uuid",
    "leadId": "AAAA0001",
    "agreement_status": "completed"
  }'
```

---



## 8. Get send agreement requirements

Returns which CRM Lead / portal fields are filled vs missing before sending an agreement.


|            |                                                                       |
| ---------- | --------------------------------------------------------------------- |
| **Method** | `GET` / `POST`                                                        |
| **Path**   | `/api/method/core.api.carrum_drivers.get_send_agreement_requirements` |




#### Parameters


| Key      | Type     | Required | Description |
| -------- | -------- | -------- | ----------- |
| `leadId` | `string` | Yes      | Lead id     |




#### Success response (`message`)


| Key             | Type            | Description                          |
| --------------- | --------------- | ------------------------------------ |
| `missing`       | `array<string>` | Labels of incomplete required fields |
| `missing_count` | `number`        | Count of missing fields              |
| `filled_count`  | `number`        | Count of filled required fields      |
| `total_count`   | `number`        | Total required fields checked        |
| `can_send`      | `boolean`       | `true` when `missing_count` is `0`   |
| `categories`    | `categories[]`  | Grouped missing fields by category   |
| `fields`        | `fields[]`      | Per-field status                     |




#### `categories[]` item


| Key              | Type       | Description                                     |
| ---------------- | ---------- | ----------------------------------------------- |
| `key`            | `string`   | `personal_bank`                                 |
| `title`          | `string`   | Category display title                          |
| `missing_fields` | `fields[]` | `{ "fieldname": string, "label": string }` rows |




#### `fields[]` item


| Key         | Type      | Description                          |
| ----------- | --------- | ------------------------------------ |
| `fieldname` | `string`  | CRM Lead field name (or logical key) |
| `label`     | `string`  | Human-readable label                 |
| `category`  | `string`  | `personal_bank`                      |
| `filled`    | `boolean` | Whether the field is complete        |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.get_send_agreement_requirements?leadId=AAAA0001' \
  --header 'Authorization: <<token>>'
```

---



## 9. Send agreement


|                  |                                                      |
| ---------------- | ---------------------------------------------------- |
| **Method**       | `POST`                                               |
| **Path**         | `/api/method/core.api.carrum_drivers.send_agreement` |
| **Content-Type** | `application/json`                                   |




#### Request body


| Key             | Type     | Required | Description                                     |
| --------------- | -------- | -------- | ----------------------------------------------- |
| `leadId`        | `string` | Yes      | Lead id                                         |
| `signingMethod` | `string` | Yes      | `digital_signature` (e-sign) or `aadhaar_esign` |


Lead must have `custom_account_id` and required CRM fields (validated server-side).

#### Success response (`message`)


| Key                   | Type      | Description                         |
| --------------------- | --------- | ----------------------------------- |
| `success`             | `boolean` | `true`                              |
| `data`                | `object`  | Upstream Carrum response            |
| `external_debug_info` | `object`  | `{ "url": string, "body": object }` |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.send_agreement' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "leadId": "AAAA0001",
    "signingMethod": "digital_signature"
  }'
```



### Related: offline agreement image upload


|                  |                                                        |
| ---------------- | ------------------------------------------------------ |
| **Method**       | `POST`                                                 |
| **Path**         | `/api/method/core.api.carrum_drivers.upload_agreement` |
| **Content-Type** | `multipart/form-data`                                  |



| Key      | Type     | Required | Description     |
| -------- | -------- | -------- | --------------- |
| `leadId` | `string` | Yes      | Lead id         |
| `image`  | `file`   | Yes      | Agreement image |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.upload_agreement' \
  --header 'Authorization: <<token>>' \
  --form 'leadId="AAAA0001"' \
  --form 'image=@"<<filePath>>"'
```

---



## 10. VA / DM push APIs



### DM push (assign Driver Manager)


|                  |                                      |
| ---------------- | ------------------------------------ |
| **Method**       | `POST`                               |
| **Path**         | `/api/method/crm.api.lead.assign_dm` |
| **Content-Type** | `application/json`                   |




#### Request body

Provide **either** `custom_account_id` **or** `leadId`.


| Key      | Type     | Required | Description                   |
| -------- | -------- | -------- | ----------------------------- |
|          |          |          |                               |
| `leadId` | `string` | Yes      | CRM Lead id                   |
| `dmId`   | `string` | Yes      | Carrum Driver Manager user id |




#### Success response (`message`)


| Key       | Type     | Description             |
| --------- | -------- | ----------------------- |
| `message` | `string` | e.g. `"DM assigned"`    |
| `data`    | `object` | Upstream Carrum payload |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.assign_dm' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "leadId": "AAAA0001",
    "dmId": "dm-uuid"
  }'
```



### VA push (assign Verification Agent)

User must be authorized to update the verification agent on ERP


|                  |                                                      |
| ---------------- | ---------------------------------------------------- |
| **Method**       | `POST`                                               |
| **Path**         | `/api/method/crm.api.lead.assign_verification_agent` |
| **Content-Type** | `application/json`                                   |




#### Request body


| Key      | Type     | Required | Description                       |
| -------- | -------- | -------- | --------------------------------- |
|          |          |          |                                   |
| `leadId` | `string` | Yes      | CRM Lead id                       |
| `vaId`   | `string` | Yes      | Carrum Verification Agent user id |




#### Success response (`message`)


| Key       | Type     | Description                          |
| --------- | -------- | ------------------------------------ |
| `message` | `string` | e.g. `"Verification Agent assigned"` |
| `data`    | `object` | Upstream Carrum payload              |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.assign_verification_agent' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "leadId": "AAAA0001",
    "vaId": "va-uuid"
  }'
```



## 11. Update requested cars


|                  |                                                          |
| ---------------- | -------------------------------------------------------- |
| **Method**       | `POST`                                                   |
| **Path**         | `/api/method/crm.api.lead.lead_vehicle_update_requested` |
| **Content-Type** | `application/json`                                       |




#### Request body


| Key                   | Type            | Required | Description                                      |
| --------------------- | --------------- | -------- | ------------------------------------------------ |
| `lead_id`             | `string`        | Yes      | Lead id                                          |
| `requested_cars_list` | `array<object>` | Yes      | List of car-type count deltas (must be an array) |




#### `requested_cars_listItem[]` item


| Key           | Type     | Required | Description |
| ------------- | -------- | -------- | ----------- |
|               |          |          |             |
| `car_type_id` | `string` | Yes      | Car type id |
| `count`       | `number` | Yes      | Delta value |




#### Success response (`message`)


| Key       | Type     | Description                     |
| --------- | -------- | ------------------------------- |
| `message` | `string` | e.g. `"Requested cars updated"` |
| `data`    | `object` | Upstream Carrum payload         |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.lead_vehicle_update_requested' \
--header 'Authorization: <<token>>' \
--header 'Content-Type: application/json' \
--data '{
    "lead_id": "FACV3462",
    "requested_cars_list": [
        {
            "car_type_id": "d8d7c48b-747d-11f1-b1c0-0a2a4959352b",
            "count": 1
        }
    ]
}'
```

---



## 12. Auto-assign API


|                  |                                                     |
| ---------------- | --------------------------------------------------- |
| **Method**       | `POST`                                              |
| **Path**         | `/api/method/crm.api.lead.lead_vehicle_auto_assign` |
| **Content-Type** | `application/json`                                  |




#### Request body


| Key                    | Type                     | Required | Description                       |
| ---------------------- | ------------------------ | -------- | --------------------------------- |
| `lead_id`              | `string`                 | Yes      | Lead id                           |
| `vendor_count_details` | `vendor_count_details[]` | Yes      | Non-empty list of car-type counts |
| `requestor_id`         | `string`                 | No       | Carrum portal user id             |




#### `vendor_count_details[]` item


| Key                    | Type     | Required | Description     |
| ---------------------- | -------- | -------- | --------------- |
| `car_type_id`          | `string` | Yes      | Car type id     |
| `passed_vehicle_count` | `number` | Yes      | Count to assign |




#### Success response (`message`)


| Key        | Type      | Description             |
| ---------- | --------- | ----------------------- |
| `is_valid` | `boolean` | `true` on success       |
| `message`  | `string`  | Status message          |
| `data`     | `object`  | Upstream Carrum payload |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.lead_vehicle_auto_assign' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "lead_id": "AAAA0001",
    "requestor_id": "portal-user-uuid",
    "vendor_count_details": [
      { "car_type_id": "sedan-uuid", "passed_vehicle_count": 1 }
    ]
  }'
```

---



## 13. Cancel auto-assign API


|                  |                                                        |
| ---------------- | ------------------------------------------------------ |
| **Method**       | `POST`                                                 |
| **Path**         | `/api/method/crm.api.lead.lead_vehicle_cancel_request` |
| **Content-Type** | `application/json`                                     |




#### Request body


| Key          | Type     | Required | Description                                  |
| ------------ | -------- | -------- | -------------------------------------------- |
| `request_id` | `string` | Yes      | Vehicle request id from portal / assignments |




#### Success response (`message`)


| Key       | Type     | Description                |
| --------- | -------- | -------------------------- |
| `message` | `string` | e.g. `"Request cancelled"` |
| `data`    | `object` | Upstream Carrum payload    |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.lead_vehicle_cancel_request' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "request_id": "request-uuid",
    "lead_id": "AAAA0001"
  }'
```

---

---



## Satellite Hub

**Method:** `GET`
**Path:** `/api/method/core.api.carrum_hubs.get_satellite_hubs`

Fetch satellite hubs from the Carrum portal (`GET /api/v1/hub/satellite`).

### Query / body parameters


| Name     | Type     | Required | Description                                |
| -------- | -------- | -------- | ------------------------------------------ |
| `hub_id` | `string` | No       | Filter satellites belonging to this hub ID |




### Success response (`message`)


| Key        | Type     | Description                             |
| ---------- | -------- | --------------------------------------- |
| `is_valid` | `bool`   | `true`                                  |
| `message`  | `string` | `"Satellite hubs fetched successfully"` |
| `data`     | `object` | Raw portal response                     |




### Failure response (`message`)


| Key        | Type     | Description                         |
| ---------- | -------- | ----------------------------------- |
| `is_valid` | `bool`   | `false`                             |
| `message`  | `string` | Portal / configuration error reason |
| `data`     | `object` | `{}`                                |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_hubs.get_satellite_hubs?hub_id=HUB-001' \
  --header 'Authorization: <<token>>'
```

---



## Uber ID Verify

**Method:** `POST`
**Path:** `/api/method/core.api.carrum_drivers.verify_uber_id`

Verify a driver's Uber ID against the Carrum portal (`POST /api/v1/driver/checkUberId`).

### Body parameters (JSON)


| Name        | Type     | Required | Description                                                              |
| ----------- | -------- | -------- | ------------------------------------------------------------------------ |
| `uber_id`   | `string` | Yes      | The driver's Uber UUID to verify                                         |
| `driver_id` | `string` | No*      | Carrum driver account ID. Required unless `lead_id` is provided.         |
| `lead_id`   | `string` | No*      | CRM Lead name; `custom_account_id` from the lead is used as `driver_id`. |


 At least one of `driver_id` or `lead_id` must be supplied.

### Success response (`message`)


| Key        | Type     | Description                                       |
| ---------- | -------- | ------------------------------------------------- |
| `is_valid` | `bool`   | `true`                                            |
| `message`  | `string` | Portal success message (e.g. `"Uber ID matched"`) |
| `data`     | `object` | Raw portal response body                          |




### Failure response (`message`)


| Key        | Type     | Description                             |
| ---------- | -------- | --------------------------------------- |
| `is_valid` | `bool`   | `false`                                 |
| `message`  | `string` | Reason (portal error, HTTP error, etc.) |
| `data`     | `object` | Raw portal error body                   |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_drivers.verify_uber_id' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{
    "uber_id": "uber-uuid-here",
    "driver_id": "carrum-driver-uuid"
  }'
```

---



## Car Type List

**Method:** `GET`
**Path:** `/api/method/core.api.carrum_vehicles.get_car_types`

Fetch all available car types from the Carrum portal (`GET /api/v1/fleet/car_types/all`).

No request parameters.

### Success response (`message`)


| Key              | Type     | Description                        |
| ---------------- | -------- | ---------------------------------- |
| `is_valid`       | `bool`   | `true`                             |
| `message`        | `string` | `"Car types fetched successfully"` |
| `data.car_types` | `array`  | List of car type objects           |




### Failure response (`message`)


| Key        | Type     | Description                |
| ---------- | -------- | -------------------------- |
| `is_valid` | `bool`   | `false`                    |
| `message`  | `string` | Portal / HTTP error reason |


```bash
curl --location '<<baseUrl>>/api/method/core.api.carrum_vehicles.get_car_types' \
  --header 'Authorization: <<token>>'
```

---



## Scheme List

**Method:** `GET` / `POST`
**Path:** `/api/method/core.api.carrum_scheme.get_scheme_list`

Fetches the alias-based scheme list for a hub from the Carrum portal (`GET /api/v1/scheme/alias?hub_id=…`). This is the API used by the CRM scheme picker.

> For the full scheme catalogue (bulk fetch), use `core.api.carrum_scheme.get_schemes_by_hub` with `hub_id` — wraps `GET /api/v1/scheme/get?hub_id=…&limit=10000`.



### Parameters (query string or JSON body)


| Name               | Type     | Required | Description                              |
| ------------------ | -------- | -------- | ---------------------------------------- |
| `businessTypeId`   | `string` | Yes*     | Hub / business-type ID to filter schemes |
| `business_type_id` | `string` | Yes*     | Snake-case alias for `businessTypeId`    |


 At least one of `businessTypeId` or `business_type_id` must be supplied.

### Success response (`message`)


| Key        | Type     | Description                                     |
| ---------- | -------- | ----------------------------------------------- |
| `is_valid` | `bool`   | `true`                                          |
| `data`     | `object` | Raw portal response from `/api/v1/scheme/alias` |
| `_debug`   | `object` | Request debug info                              |




### Missing-param response (`message`)

Returned (HTTP 200) when `businessTypeId` / `business_type_id` is absent:

```json
{ "is_valid": false, "reason": "Business Type Id is required" }
```

```bash
# GET (query param)
curl --location '<<baseUrl>>/api/method/core.api.carrum_scheme.get_scheme_list?businessTypeId=HUB-001' \
  --header 'Authorization: <<token>>'

# POST (JSON body)
curl --location '<<baseUrl>>/api/method/core.api.carrum_scheme.get_scheme_list' \
  --header 'Authorization: <<token>>' \
  --header 'Content-Type: application/json' \
  --data '{"businessTypeId": "HUB-001"}'
```

---



## EMI List

**Method:** `GET`
**Path:** `/api/method/crm.api.lead.get_emis`

Fetches EMI plans available for a scheme-car-type combination from the Carrum portal (`GET /api/v1/scheme/scheme_car_type/{id}/emi`).

### Query / body parameters


| Name                 | Type     | Required | Description                               |
| -------------------- | -------- | -------- | ----------------------------------------- |
| `scheme_car_type_id` | `string` | Yes      | Scheme-car-type ID to fetch EMI plans for |




### Success response (`message`)


| Key       | Type     | Description                                      |
| --------- | -------- | ------------------------------------------------ |
| `message` | `string` | `"EMIs fetched"`                                 |
| `data`    | `array`  | List of EMI plan objects (`results` from portal) |
| `_debug`  | `object` | Request debug info                               |




### Failure response (`message`)

Returned when the portal returns a non-OK HTTP status:


| Key        | Type     | Description                                      |
| ---------- | -------- | ------------------------------------------------ |
| `is_valid` | `bool`   | `false`                                          |
| `message`  | `string` | `"EMIs fetched"` *(known quirk in current code)* |
| `data`     | `array`  | `[]`                                             |
| `_debug`   | `object` | Request debug info                               |


```bash
curl --location '<<baseUrl>>/api/method/crm.api.lead.get_emis?scheme_car_type_id=SCT-001' \
  --header 'Authorization: <<token>>'
```

---



## Get Lead by Lead Id



## Find or Create Lead



## Update Lead



## Get Agent By Id



## Verify Uber Id



## Satellite Hub List



## Quick index


| #   | Capability                      | Method | Path                                                                  |
| --- | ------------------------------- | ------ | --------------------------------------------------------------------- |
| —   | Lead — Find or Create           | `POST` | `/api/method/core.api.lead.find_or_create_lead`                       |
| —   | Lead — Update                   | `POST` | `/api/method/core.api.lead.update_lead`                               |
| —   | Lead — Get                      | `GET`  | `/api/method/core.api.lead.get_lead`                                  |
| 1   | Document upload                 | `POST` | `/api/method/upload_file`                                             |
| 2   | Generate payment link           | `POST` | `/api/method/core.api.carrum_payment.send_payment_link`               |
| 3   | Add other payment               | `POST` | `/api/method/core.api.carrum_payment.add_other_payment`               |
| 4   | Add cash payment                | `POST` | `/api/method/core.api.carrum_payment.add_cash`                        |
| 5   | Add cheque payment              | `POST` | `/api/method/crm.api.lead.submit_cheque`                              |
| 6   | Agreement list                  | `GET`  | `/api/method/core.api.carrum_drivers.get_driver_agreements`           |
| 7   | Mark agreement status           | `POST` | `/api/method/core.api.carrum_drivers.update_agreement_history_status` |
| 8   | Get send agreement requirements | `GET`  | `/api/method/core.api.carrum_drivers.get_send_agreement_requirements` |
| 9   | Send agreement                  | `POST` | `/api/method/core.api.carrum_drivers.send_agreement`                  |
| 10  | DM push                         | `POST` | `/api/method/crm.api.lead.assign_dm`                                  |
| 10b | VA push                         | `POST` | `/api/method/crm.api.lead.assign_verification_agent`                  |
| 11  | Update requested cars           | `POST` | `/api/method/crm.api.lead.lead_vehicle_update_requested`              |
| 12  | Auto-assign                     | `POST` | `/api/method/crm.api.lead.lead_vehicle_auto_assign`                   |
| 13  | Cancel auto-assign              | `POST` | `/api/method/crm.api.lead.lead_vehicle_cancel_request`                |
| 14  | Satellite hubs                  | `GET`  | `/api/method/core.api.carrum_hubs.get_satellite_hubs`                 |
| 15  | Uber ID verify                  | `POST` | `/api/method/core.api.carrum_drivers.verify_uber_id`                  |
| 16  | Scheme list (alias)             | `POST` | `/api/method/core.api.carrum_scheme.get_scheme_list`                  |
| 17  | Car type list                   | `GET`  | `/api/method/core.api.carrum_vehicles.get_car_types`                  |
| 18  | EMI list                        | `GET`  | `/api/method/crm.api.lead.get_emis`                                   |


