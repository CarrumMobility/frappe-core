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
file_storage_type: DEFAULT|S3
aws_access_key_id: str
aws_secret_access_key: str
s3_bucket: str
s3_bucket_prefix: str
s3_region: str
s3_endpoint_url: str
login_url: str
desk_url: str
```

## File storage

`file_storage_type` selects exactly one backend:

- `DEFAULT` (or an omitted key) uses Frappe's local filesystem.
- `S3` uses `s3_bucket` and optional `s3_region`, `s3_bucket_prefix`, `s3_endpoint_url`, and AWS-named credentials.

To use Google Cloud Storage, keep `file_storage_type: "S3"`, set `s3_endpoint_url` to `https://storage.googleapis.com`, put GCS HMAC keys in `aws_access_key_id` / `aws_secret_access_key`, and set `s3_bucket` to the GCS bucket name. Dedicated `gcs_*` keys and `file_storage_type: "GCS"` are not supported.

Changing endpoint, bucket, or credentials does not migrate existing objects. Update config only after the target backend contains the files the site needs to access.

### Documentation

- Product / cutover outcomes: [docs/product/file_storage.md](docs/product/file_storage.md)
- Technical architecture and AWS→GCS endpoint cutover: [docs/technical/file_storage.md](docs/technical/file_storage.md)
