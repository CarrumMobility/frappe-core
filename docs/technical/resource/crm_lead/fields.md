# CRM Lead — Field Reference

**DocType:** `CRM Lead`  
**See also:** [README](README.md) · [GET](get.md) · [POST](post.md) · [PUT](put.md)

---

## Identity & classification

| Field | Type | Writable | Notes |
|---|---|---|---|
| `name` | Data (PK) | Insert only | Auto `AAAA0001`–`ZZZZ9999` |
| `lead_name` | Data | Yes | Display name |
| `salutation` | Link → Salutation | Yes | Hidden in UI |
| `gender` | Link → Gender | Yes | |
| `mobile_no` | Data | Yes* | 10-digit Indian; unique. *Telecaller restrictions |
| `mask_mobile_no` | Data | No | Auto: `**` + last 8 digits |
| `alternate_phone` | Data | Yes | |
| `email` | Data | Yes | Validated |
| `lead_type` | Select | Yes | `LEAD` \| `DRIVER` \| `VENDOR` |
| `image` | Attach Image | Yes | Hidden |

## Status & disposition

| Field | Type | Writable | Notes |
|---|---|---|---|
| `status` | Link → CRM Lead Status | Yes | FK; synced from primary/secondary |
| `primary_status` | Data | Yes | e.g. `New`, `Interested`, `Drop`, `Converted` |
| `secondary_status` | Data | Yes | Sub-disposition |
| `last_remarks` | Text | Yes | Last agent comment |
| `converted` | Check | No | Conversion flows |
| `lost_reason` | Link → CRM Lost Reason | Yes | |
| `lost_notes` | Text | Yes | Required when `lost_reason = Other` |

## Hub & visit

| Field | Type | Writable | Notes |
|---|---|---|---|
| `hub_id` | Data | Yes | Carrum hub UUID |
| `custom_hub_name` | Data | Yes | Hub display name |
| `hub_visit_status` | Select | Yes | `NOT_IN_HUB` \| `IN_HUB` \| `HUB_VISITED` |
| `gate_ticket_no` | Data | Yes | Gate App ticket |
| `custom_gate_ticket_generated_at` | Datetime | No | Gate App |
| `hubvisit_category` | Data | Yes | |
| `hubvisit_subcategory` | Data | Yes | |
| `walkin_form_filled_at` | Datetime | Yes | Last walk-in time |
| `walkin_form_link` | Link → Lead walkin done | Yes | Latest walk-in record |
| `total_walkin_forms_filled` | Int | Yes | Repeat-visit counter |

## Source & attribution

| Field | Type | Writable | Notes |
|---|---|---|---|
| `source` | Data | Yes | Source label |
| `source_id` | Link → CRM Lead Source | Yes | |
| `upload_source` | Data | Yes | Bulk upload |
| `telecaller` | Link → User | Yes | |
| `driver_manager` | Link → User | Yes | |
| `primary_lead` | Link → CRM Lead | Yes | Vendor / secondary → primary |
| `merged_into_lead_id` | Link → CRM Lead | No | Merge action |

## Portal / driver sync

| Field | Type | Writable | Notes |
|---|---|---|---|
| `custom_account_id` | Data | Yes | Carrum account ID |
| `business_type_id` / `business_type_name` | Data | Yes | |
| `car_type_id` | Data | Yes | |
| `scheme_id` | Data | Yes | |
| `referral_scheme_id` | Data | Yes | |
| `preferred_business_type_1/2` | Data | Yes | |
| `preferred_scheme_1/2` | Data | Yes | |
| `uber_id` | Data | Yes | |
| `uber_id_status` | Select | Yes | `PENDING` \| `BLOCKED` \| `DONE` |
| `uber_rating` | Data | Yes | |
| `total_paid_amount` | Currency | No | Portal sync |
| `psd_received_at` / `fsd_received_at` | Datetime | Yes | |

## KYC & documents

| Field | Type | Writable | Notes |
|---|---|---|---|
| `aadhar_no` | Data | Yes | Unique |
| `pancard_number` | Data | Yes | Unique |
| `driving_license_number` | Data | Yes | Unique |
| `driving_license_status` | Select | Yes | |
| `driving_license_issue_date` / `expiry_date` | Date | Yes | |
| `document_status` | Select | No | Auto from attachments |
| `aadhaar_card_front/back` | Attach | Yes | |
| `driving_license_front/back` | Attach | Yes | |
| `pancard_pic` | Attach | Yes | |
| `bank_passbook_pic` | Attach | Yes | |
| `current_address_proof` | Attach | Yes | |
| `bank_account_number` / `bank_ifsc` | Data | Yes | |
| `current_address_line1/2` | Text | Yes | |
| `current_city/state/country/pincode/landmark` | Data | Yes | |
| `current_address_number` | Text | Yes | |
| `current_address_proof_type` | Select | Yes | |
| `location_link` | Data | Yes | Validated URL |
| `address` | Text | Yes | |
| `hub_fee` | Float | Yes* | *Immutable after first save |
| `preferred_lang` | Select | Yes | |

## Facebook sync

| Field | Type | Writable | Notes |
|---|---|---|---|
| `facebook_lead_id` | Data | Yes | Unique |
| `facebook_form_id` | Data | Yes | |
| `facebook_raw_data` | JSON | Yes | |

## Telephony & tags

| Field | Type | Writable | Notes |
|---|---|---|---|
| `last_call_date` / `last_call_time` | Date/Time | No | |
| `redial_time` | Datetime | No | |
| `user_tags` | Data | Yes | Privacy-filtered on read |
| `lead_uploaded_at` | Datetime | No | |

## Phone normalization

APIs normalizing phone input use `normalize_crm_lead_india_phone`:

- Strips non-digits; removes leading `91`; removes trunk `0` on 11-digit input
- `mobile_no` first digit must be 6–9
- Stored as 10 digits without `+91`
