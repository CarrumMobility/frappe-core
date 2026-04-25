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
aws_access_key_id: str
aws_secret_access_key: str
s3_bucket: str
s3_bucket_prefix: str
s3_file_storage_enabled: 0|1
s3_region: str,
login_url: str
desk_url: str
```
