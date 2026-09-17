# File storage (product)

**Supported backends:** Local filesystem (`DEFAULT`), object storage via S3 API (`S3`)  
**Owner:** Core platform  
**Audience:** Admins and operators configuring sites

`S3` covers Amazon S3 and S3-compatible providers. Google Cloud Storage cutover uses the same `S3` selector with a GCS endpoint and HMAC credentials — not a separate `GCS` storage type.

## What this controls

Where new File uploads are stored and where Core reads/deletes them from for that site.

```json
"file_storage_type": "DEFAULT" | "S3"
```

| Value | Meaning |
|---|---|
| `DEFAULT` (or omit the key) | Files on the site's local disk |
| `S3` | One object bucket via boto3 (Amazon S3, or GCS with `s3_endpoint_url`) |

## Who should care

- **Admins** planning a cutover from Amazon S3 to GCS, or from local disk to cloud
- **Operators** validating upload / open / delete after a config change

## Important product rules

Changing `file_storage_type` or flipping endpoint/bucket/credentials does **not** move existing objects. Old files remain where they were stored. Align config with where those files live, or run a separate object migration first.

## Cutover recipes

### Enable Amazon S3

1. Provision the bucket and credentials.
2. Set `s3_bucket`, optional `s3_bucket_prefix` / `s3_region`, and AWS keys.
3. Set `"file_storage_type": "S3"`.
4. Restart and smoke-test upload, open, delete.

### Move Amazon S3 → Google Cloud Storage (minimal)

Stay on `"file_storage_type": "S3"`. Do **not** introduce `gcs_*` keys or `file_storage_type: "GCS"`.

1. Provision the GCS bucket, service account, and **HMAC keys**.
2. Copy objects with the same key layout if historical Files must keep working.
3. Update site config:
   - `s3_endpoint_url`: `https://storage.googleapis.com`
   - `s3_bucket`: GCS bucket name
   - `aws_access_key_id` / `aws_secret_access_key`: HMAC values
   - optional `s3_bucket_prefix` for public/CDN URLs
4. Restart and smoke-test upload, open, delete.

### Stay on local disk

Omit `file_storage_type` or set `"file_storage_type": "DEFAULT"`.

## Validation expectations

- Values are strict uppercase: `DEFAULT`, `S3`. Lowercase or typos fail validation.
- `GCS` as a selector fails with a migration message pointing to `S3` + `s3_endpoint_url`.
- Incomplete cloud config (for example `S3` without `s3_bucket`) fails the operation. Files are not written locally as a fallback.

## GCS product constraints (via S3 mode)

- No separate GCS selector or `gcs_*` site keys.
- No dedicated GCS region key in site config; bucket location is set in Google Cloud when the bucket is created.
- Authentication uses **HMAC keys** in the existing `aws_*` fields against `https://storage.googleapis.com`.
- Optional `s3_bucket_prefix` is only for public URL presentation. Private files continue to use Frappe-style paths when no prefix applies.

## Smoke-test checklist (GCS endpoint)

With `file_storage_type: "S3"` and `s3_endpoint_url: "https://storage.googleapis.com"`:

- [ ] Upload a File
- [ ] Open / download it
- [ ] Delete it and confirm the object is gone from the bucket
