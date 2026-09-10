# Core
This is core dependency around the frappe framework based repository, [Crm](https://github.com/CarrumMobility/frappe-crm), [Chatwoot Integration](https://github.com/CarrumMobility/frappe_chatwoot)

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app core
```

## Additional environment variables
```python
db_name: str,
db_password:str,
db_type: str,
developer_mode: bool,
encryption_key: str
master_password: str
chatwoot_account_id: int
chatwoot_base_url: str
carrum_base_url: str
carrum_token: str
file_storage_type: DEFAULT|S3|GCS
aws_access_key_id: str
aws_secret_access_key: str
s3_bucket: str
s3_bucket_prefix: str
s3_region: str,
gcs_bucket: str
gcs_bucket_prefix: str
login_url: str
desk_url: str
```

## File storage

`file_storage_type` selects exactly one backend:

- `DEFAULT` (or an omitted key) uses Frappe's local filesystem.
- `S3` uses `s3_bucket` and the existing optional S3 region, URL prefix, and AWS credentials.
- `GCS` uses one `gcs_bucket` and an optional `gcs_bucket_prefix`.

GCS authentication uses [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) from the runtime environment. Do not put service-account JSON in `site_config.json`. GCS does not require a region key; bucket location is configured when the bucket is created.

Changing `file_storage_type` does not migrate existing objects. Update the selector only after the target backend contains the files the site needs to access.

### Documentation

- Product / cutover outcomes: [docs/product/file_storage.md](docs/product/file_storage.md)
- Technical architecture and GCS migration runbook: [docs/technical/file_storage.md](docs/technical/file_storage.md)
