import frappe
from pydantic import BaseModel, model_validator

from core.file_storage import FileStorageType
from core.services.util_service import publish_docs as publish_docs_to_website


# Env config validation schema using pydantic
class EnvConfig(BaseModel):
    master_password: str
    chatwoot_account_id: int
    chatwoot_base_url: str
    carrum_base_url: str
    carrum_token: str
    db_name: str
    db_password: str
    db_type: str
    allow_tests: bool
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    carrum_base_url: str
    carrum_token: str
    chatwoot_account_id: int
    chatwoot_base_url: str
    developer_mode: bool
    encryption_key: str
    env: str
    master_password: str
    old_carrum_base_url: str
    old_carrum_token: str
    file_storage_type: FileStorageType = FileStorageType.DEFAULT
    gcs_bucket: str | None = None
    gcs_bucket_prefix: str | None = None
    s3_bucket: str | None = None
    s3_bucket_prefix: str | None = None
    s3_region: str | None = None
    smartflo_admin_password: str
    smartflo_admin_username: str

    @model_validator(mode="after")
    def validate_file_storage_config(self):
        if self.file_storage_type == FileStorageType.S3:
            if not (self.s3_bucket or "").strip():
                raise ValueError("s3_bucket is required when file_storage_type is S3")

            has_access_key = bool((self.aws_access_key_id or "").strip())
            has_secret_key = bool((self.aws_secret_access_key or "").strip())
            if has_access_key != has_secret_key:
                raise ValueError(
                    "aws_access_key_id and aws_secret_access_key must either both be set or both be omitted"
                )
        elif self.file_storage_type == FileStorageType.GCS and not (self.gcs_bucket or "").strip():
            raise ValueError("gcs_bucket is required when file_storage_type is GCS")
        return self

def validateConfig():
    return EnvConfig(**frappe.conf)

@frappe.whitelist()
def get_env_config():
    try:
        config = validateConfig()
    except Exception as e:
        return {
            "isValid": False,
            "error": f"Invalid config: {e!s}"
        }

    return {
        "isValid": True,
        "configs": config.model_dump()
    }

@frappe.whitelist(allow_guest=True)
def emit_socket_event(event: str, payload: dict):
    frappe.publish_realtime(event, payload)



@frappe.whitelist(methods=["POST"])
def publish_docs():
	"""Publish markdown docs from core/docs as website pages at /docs/{category}/{file_name}."""
	frappe.only_for("System Manager")
	return publish_docs_to_website()
