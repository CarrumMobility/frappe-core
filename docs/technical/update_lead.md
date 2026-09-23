# `core.api.lead.update_lead` — Field Reference

**Method:** `POST`
**Path:** `/api/method/core.api.lead.update_lead`

Body: `lead_id` (string), `updates` (object, partial — only sent keys are applied), `lsq_id` (string, optional).

## `updates` fields

| Field | Type | Description |
|---|---|---|
| `lead_name` | string | Driver / lead full name |
| `mobile_no` | string | Primary mobile number |
| `email` | string | Email address |
| `gender` | string | Gender |
| `alternate_phone` | string | Secondary phone number |
| `preferred_lang` | string | Preferred language |
| `lead_type` | string | `DRIVER`, `LEAD`, or `VENDOR` |
| `primary_status` | string | Primary status bucket |
| `secondary_status` | string | Secondary status |
| `status` | string | CRM Lead Status name |
| `hub_visit_status` | string | `NOT_IN_HUB`, `IN_HUB`, or `HUB_VISITED` |
| `uber_id_status` | string | Uber ID verification status |
| `uber_id` | string (UUID) | Uber ID — portal-only, forwarded to Carrum, not stored on CRM Lead |
| `driving_license_status` | string | DL verification status |
| `hub_id` | string | Assigned hub ID |
| `custom_hub_name` | string | Assigned hub display name |
| `telecaller` | string | Telecaller user |
| `driver_manager` | string | Driver Manager user |
| `primary_lead` | string | Linked primary lead (for secondary leads) |
| `source` | string | Lead source |
| `source_id` | string | Lead source reference |
| `user_tags` | string | User tags |
| `aadhar_no` | string | Aadhaar number |
| `pancard_number` | string | PAN number |
| `driving_license_number` | string | DL number |
| `driving_license_issue_date` | date (`YYYY-MM-DD`) | DL issue date |
| `driving_license_expiry_date` | date (`YYYY-MM-DD`) | DL expiry date |
| `uber_rating` | string | Uber rating |
| `address` | string | Free-form address |
| `current_address_line1` | string | Current address line 1 |
| `current_address_line2` | string | Current address line 2 |
| `current_city` | string | Current city |
| `current_state` | string | Current state |
| `current_country` | string | Current country |
| `current_pincode` | string | Current pincode |
| `current_landmark` | string | Current landmark |
| `current_address_number` | string | Current address number |
| `current_address_proof_type` | string | Type of address proof provided |
| `location_link` | string | Map location link |
| `bank_account_number` | string | Bank account number |
| `bank_ifsc` | string | Bank IFSC code |
| `aadhaar_card_front` | string (file URL) | Aadhaar front image |
| `aadhaar_card_back` | string (file URL) | Aadhaar back image |
| `driving_license_front` | string (file URL) | DL front image |
| `driving_license_back` | string (file URL) | DL back image |
| `driver_partner_selfie` | string (file URL) | Driver selfie |
| `pancard_pic` | string (file URL) | PAN card image |
| `bank_passbook_pic` | string (file URL) | Bank passbook image |
| `current_address_proof` | string (file URL) | Address proof image |
| `image` | string (file URL) | Profile picture |
| `business_type_id` | string | Business type ID |
| `business_type_name` | string | Business type name |
| `car_type_id` | string | Car type ID |
| `scheme_id` | string \| number | Scheme ID — dual-written to CRM Lead and Carrum |
| `scheme_name` | string | Scheme name |
| `referral_scheme_id` | string | Referral scheme ID |
| `preferred_business_type_1` | string | Preferred business type (1st choice) |
| `preferred_scheme_1` | string | Preferred scheme (1st choice) |
| `preferred_business_type_2` | string | Preferred business type (2nd choice) |
| `preferred_scheme_2` | string | Preferred scheme (2nd choice) |
| `scheme_type` | string | Scheme type — portal-only, forwarded to Carrum |
| `old_scheme_name` | string | Previous scheme name — used to detect leaving a vendor/double-driver scheme, not sent to Carrum |
| `tenure` | int | EMI tenure — portal-only; must be sent together with `emi_id` |
| `emi_id` | string | EMI plan ID — portal-only; must be sent together with `tenure` |
| `remove_emi` | boolean | Remove the driver's EMI — portal-only |
| `gate_ticket_no` | string | Gate ticket number |
| `hubvisit_category` | string | Hub visit category |
| `hubvisit_subcategory` | string | Hub visit subcategory |
