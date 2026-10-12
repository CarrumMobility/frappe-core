# Plan: Pazy client in core + unique S3 URLs from pdf_service

Spec: user request (2026-10-07), on top of the Pazy invoice-sync work
(ClickUp 86d49v4dm, tech design "Automatic Invoice PDF Upload to Pazy"):

1. Move the Pazy client to core, following the existing integrations
   (`core/integrations/callmatic`, `chatwoot`, `olx`, `smartflo`).
2. `core.services.pdf_service` must produce the S3 URL, and the URL must be
   unique every time, even when the same HTML is rendered more than once.

## Context

Bench root: `/Users/kapilrohilla/carrum/crm-bench`. Two git repos are involved,
both on local branch `kapil/pazy-invoice-pdf`:

- core: `apps/core` (python package `core`)
- crm:  `apps/crm`  (python package `crm`)

Run tests from the bench root:
`bench --site dev run-tests --module <dotted.module>` (site `dev` has `allow_tests`).
Lint: `ruff check <paths>` and `ruff format <paths>` inside the repo (tabs, line length 110).
Redis is not running; tests must not need it (mock `frappe.enqueue` / api-hit logging).

## Global Constraints

- core must never import from crm (core is the lower layer).
- Match surrounding style: tabs, `from __future__ import annotations`, short docstrings.
- Outbound API calls are logged via `core.services.apihit_service.api_hit_service.log_api_request`;
  never log the API key, the Authorization header, or the PDF bytes.
- The Pazy API key stays in site config as `pazy_api_key`.
- Tests use mocks only: no real HTTP, no real S3, and no File rows left behind in the DB.
- Commit each task on branch `kapil/pazy-invoice-pdf` in the repo(s) it touches; do not push.
  End commit messages with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Task 1: Pazy client in core/integrations/pazy

Today the client lives at `apps/crm/crm/module_maintenance/invoice_sync/pazy_client.py`
(module-level `create_invoice(pdf_bytes, filename, remarks, base_url=None, timeout_seconds=None) -> dict`,
`PazyClientError(InvoiceSyncError)`), and is used by
`apps/crm/crm/module_maintenance/invoice_sync/sync.py::_upload`. Its tests are the
`TestPazyClient` class in `apps/crm/crm/module_maintenance/invoice_sync/tests/test_invoice_sync.py`.
Read the existing core clients (`core/integrations/callmatic/client.py`, `core/integrations/olx/client.py`)
for the house pattern: a client class wrapping requests plus an `<Name>ApiError` exception.

Create in core:

- `core/integrations/pazy/__init__.py` (empty)
- `core/integrations/pazy/client.py` with:
  - constants `PAZY_DEFAULT_BASE_URL = "https://api.pazy.io/v1.0"`,
    `PAZY_DEFAULT_TIMEOUT_SECONDS = 60`, `PAZY_MAX_INVOICE_FILE_BYTES = 50 * 1024 * 1024`
  - `class PazyApiError(Exception)` with keyword attributes `status_code: int | None`,
    `code: str | None`, `response_body` (same pattern as `OlxApiError`)
  - `get_pazy_api_key() -> str`: `(frappe.conf.get("pazy_api_key") or "").strip()`
  - `class PazyClient`:
    - `__init__(self, api_key: str | None = None, *, base_url: str | None = None, timeout_seconds: int | None = None)`;
      `api_key` defaults to `get_pazy_api_key()`, base URL and timeout default to the constants
    - `create_invoice(self, pdf_bytes: bytes, filename: str, remarks: str, *, user: str | None = None) -> dict`:
      behaviour identical to today's crm `create_invoice`: missing key -> error; file larger than the max -> error;
      `POST {base_url}/invoice` multipart (`file` = (filename, bytes, "application/pdf"), `remarks` form field),
      header `Authorization: Api-Key <key>`; timeout -> error with `code="TIMEOUT"`; other request
      exception -> `code="REQUEST_FAILED"`; non-200 -> error carrying Pazy's `error.code`
      (413 -> `PAYLOAD_TOO_LARGE` when Pazy gives no code); 200 without `ok` and `data.id` -> `code="UNEXPECTED_RESPONSE"`;
      success returns the response's `data` dict. Every attempt (success or failure) is logged once with
      api_name `"Pazy:create_invoice"`, payload `{"file": filename, "file_size": len(pdf_bytes), "remarks": remarks}`,
      `created_by=created_by_user(user)`, and no headers.
    - All failures raise `PazyApiError`.

Change in crm:

- Delete `crm/module_maintenance/invoice_sync/pazy_client.py`.
- `sync.py::_upload`: use `PazyClient(base_url=settings.get("base_url"), timeout_seconds=settings.get("timeout_seconds")).create_invoice(...)`
  and return `str(data["id"])`. Behaviour of `run_invoice_sync` is unchanged (any exception -> Failed).
- Update the module docstring in `crm/module_maintenance/invoice_sync/__init__.py` that says
  "Only pazy_client.py knows about Pazy" to point at `core.integrations.pazy.client`.
- Move `TestPazyClient` out of the crm test file into `core/tests/test_pazy_client.py`
  (create `core/tests/__init__.py` if missing), adapted to `PazyClient` / `PazyApiError`.
  Keep cases: 200 ok returns data and sends `Api-Key` header and never logs the key;
  400 / 401 / 413 / 500 / 200-without-ok each raise with the right `status_code`;
  timeout raises `code == "TIMEOUT"` and is logged with the error message; missing key raises.
  The crm tests in `test_invoice_sync.py` must still pass (they patch `sync_mod._upload`).

Verify: `bench --site dev run-tests --module core.tests.test_pazy_client` and
`bench --site dev run-tests --module crm.module_maintenance.invoice_sync.tests.test_invoice_sync` pass;
`grep -rn "pazy_client" apps/crm/crm` returns nothing.

## Task 2: pdf_service stores to S3 with a unique URL per call

File: `apps/core/core/services/pdf_service.py`. Today `save_pdf` inserts a Frappe `File` with
`content=pdf_bytes`; the S3 write hook (`core/s3_file_hooks.py::write_file`) names the object
`{stem}_{content_hash[-12:]}{ext}`, and Frappe's File dedupe (`validate_duplicate_entry`,
`save_file`'s content-hash lookup, with `core/override/file.py::exists_on_disk` returning True for
S3 files) reuses an existing File's `file_url` when the bytes match. So identical PDF bytes can
map to the same object and URL.

Required behaviour:

- Every call of `save_pdf` / `html_to_pdf_file` / `html_to_pdf_url` creates a new File whose
  stored object and `file_url` are new and unique, even when the HTML and PDF bytes are identical
  to a previous call. The display `file_name` the caller passes stays as given (e.g.
  `Invoice_Summary_<bill>.pdf`), the stored object name gets a unique suffix.
- When S3 is enabled (`core.s3_file_storage.s3_enabled()`): pdf_service uploads the bytes itself
  with `s3_put_bytes` to a key from `build_object_key(site, is_private, unique_name)`, where
  `unique_name = f"{stem}_{frappe.generate_hash(length=16)}{ext}"`, then inserts a File record
  pointing at `public_file_url(key)` (no `content`, so the write hook and content-hash dedupe do not run),
  with `file_size`, `is_private`, and the attached_to fields set. `file_url` is therefore the S3 URL.
- When S3 is disabled (local dev): fall back to a Frappe File with content, still with the unique
  stored name, and with Frappe's duplicate reuse disabled so the URL is unique per call. Log nothing
  extra; this path exists so local dev keeps working.
- `html_to_pdf_url` returns an absolute URL (`absolute_file_url`, unchanged).
- `read_file_bytes(file_doc)` must keep working for both kinds of File (crm `pdf_builder` uses it to
  re-upload a stored PDF on retry).
- Public signatures of `render_html`, `html_to_pdf`, `save_pdf`, `html_to_pdf_file`, `html_to_pdf_url`,
  `read_file_bytes`, `absolute_file_url` stay compatible (crm's
  `crm/module_maintenance/invoice_sync/pdf_builder.py` calls `html_to_pdf_file` and `read_file_bytes`).
- Update the module docstring to state the uniqueness guarantee.

Tests: `core/tests/test_pdf_service.py` (no real S3, no wkhtmltopdf needed for the storage tests;
roll back or delete any File rows created):
- S3 enabled (patch `s3_enabled` -> True, `s3_put_bytes`, `s3_bucket_prefix`/conf so `public_file_url` yields
  an `https://` URL): two `save_pdf` calls with identical bytes and identical `file_name` return Files with
  different `file_url`s, both starting with the bucket prefix, and `s3_put_bytes` is called twice with
  different keys under `{site}/private/files/` for private files.
- S3 disabled: two calls with identical bytes return different `file_url`s.
- `html_to_pdf_url` with identical HTML twice returns two different absolute URLs (patch `html_to_pdf`
  to return fixed bytes).

Verify: `bench --site dev run-tests --module core.tests.test_pdf_service` passes, the crm invoice-sync
tests still pass, and `ruff check` is clean on touched files.
