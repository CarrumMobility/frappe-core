# Lead walkin done — Field Reference

| Field | Type | Required | Writable | Notes |
|---|---|---|---|---|
| `name` | Data (PK) | Auto | No | Hash autoname |
| `lead` | Link → CRM Lead | Yes | Yes | Parent lead |
| `lead_status_link` | Link → CRM Lead Status | Yes | Yes | Disposition row used |
| `primary_status` | Data | No | Yes | Snapshot at submit |
| `secondary_status` | Data | No | Yes | Snapshot at submit |
| `source` | Data | No | Yes | Source label snapshot |
| `remarks` | Small Text | No | Yes | Agent comment |
| `callback_at` | Datetime | No | Yes | Callback or visit datetime |
| `callback_type` | Select | No | Yes | `Callback` or `Visit Date` |
| `telecaller` | Link → User | No | Yes | Telecaller attribution |
| `business_type` | Data | No | Yes | Product interest; required in walk-in form UI for all submissions. Server falls back to lead `business_type_name` if omitted. |
| `referrer_name` | Data | No | Yes | Referral flow |
| `referrer_mobile_no` | Data | No | Yes | Referral flow |
| `referrer_user_link` | Link → User | No | Yes | Referrer user |
| `created_by` | Link → User | No | Yes | Submitting agent |
| `walkin_form_filled_at` | Datetime | Auto | Yes | Set to `creation` if blank on save |

Standard metadata: `owner`, `creation`, `modified`, `modified_by` — server-managed.
