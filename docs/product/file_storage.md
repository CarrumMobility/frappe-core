# File Storage — Product Guide

**Feature:** File storage backends  
**Status:** Available  
**Supported backends:** Local filesystem (`DEFAULT`), Amazon S3 (`S3`), Google Cloud Storage (`GCS`)  
**Technical docs:** [../technical/file_storage.md](../technical/file_storage.md)

---

## What changed?

Sites used to enable cloud file storage with a boolean flag:

```json
"s3_file_storage_enabled": 1
```

That flag could only mean “S3 on” or “S3 off”. It could not select Google Cloud Storage, and an omitted or incomplete setup quietly fell back to local disk.

Sites now choose exactly one backend with:

```json
"file_storage_type": "DEFAULT" | "S3" | "GCS"
```

| Value | Where new files go |
|---|---|
| `DEFAULT` (or key omitted) | Local Frappe filesystem |
| `S3` | Existing Core S3 bucket layout |
| `GCS` | One Google Cloud Storage bucket |

---

## Who is this for?

- **Operators / platform engineers** configuring each site’s storage backend
- **Admins** planning a cutover from S3 to GCS or from local disk to cloud
- **Product / support** explaining why attachments live in a given backend after a site change

End users uploading attachments do not choose the backend. The site configuration decides where every new File write, read, existence check, and delete goes.

---

## What users experience

1. A user uploads or attaches a file in CRM/Desk.
2. Core stores that file on the **currently selected** backend only.
3. Private files keep Frappe-style URLs such as `/private/files/...`.
4. Public cloud files use either a configured public URL prefix or the provider’s public object URL.
5. Deleting a File removes the object from the selected cloud backend (when cloud is active).

Changing `file_storage_type` does **not** move existing objects. Old files remain where they were stored. The site must keep the selector aligned with where those files live, or run a separate object migration first.

---

## Migration outcomes (product view)

### Keep S3 (config-only cutover)

Existing S3 sites must replace the legacy flag before deploying the new code:

| Before | After |
|---|---|
| `"s3_file_storage_enabled": 1` | `"file_storage_type": "S3"` |

Keep existing `s3_bucket`, `s3_bucket_prefix`, `s3_region`, and AWS keys unchanged. No file copy is required for this step.

### Move to GCS

GCS is a **new** backend for new uploads after cutover. Object data is not copied automatically.

Before flipping the selector:

1. Provision the GCS bucket and IAM for Application Default Credentials.
2. Configure `gcs_bucket` (required) and optional `gcs_bucket_prefix`.
3. Copy or recreate any files the site still needs to read (separate migration).
4. Set `"file_storage_type": "GCS"`.
5. Smoke-test upload, open/download, and delete.

### Stay on local disk

Omit `file_storage_type` or set `"file_storage_type": "DEFAULT"`.

---

## Breaking behavior to communicate

- `s3_file_storage_enabled` no longer enables S3. Leaving only that flag active treats the site as `DEFAULT` (local disk).
- Values are strict uppercase: `DEFAULT`, `S3`, `GCS`. Lowercase or typos fail validation; they do not silently fall back.
- Incomplete cloud config (for example GCS selected without `gcs_bucket`) fails the operation. Files are not written locally as a fallback.
- A site cannot read the same File from both S3 and GCS after changing the selector unless the objects were migrated separately.

---

## GCS product constraints

- One bucket per site for both private and public files; privacy is expressed by object key path (`.../private/files/...` vs `.../files/...`).
- No `gcs_region` site key. Bucket location is set when the bucket is created in Google Cloud.
- No service-account JSON in `site_config.json`. Authentication uses Application Default Credentials in the runtime environment.
- Optional `gcs_bucket_prefix` is only for public URL presentation (CDN or custom host). Private files continue to use Frappe-style paths.

---

## Success criteria after cutover

- New uploads appear only in the selected backend.
- Existing files needed by the business remain openable after cutover.
- Delete removes the cloud object when cloud storage is selected.
- Inactive backends receive no new writes for that site.

---

## Related docs

- Technical architecture, config keys, and operator cutover: [../technical/file_storage.md](../technical/file_storage.md)
- Core app overview / env keys: [../../README.md](../../README.md)
