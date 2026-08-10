import frappe
from pydantic import BaseModel

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
    aws_access_key_id: str
    aws_secret_access_key: str
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
    s3_bucket: str
    s3_bucket_prefix: str
    s3_file_storage_enabled: bool
    s3_region: str
    smartflo_admin_password: str
    smartflo_admin_username: str

def validateConfig():
    return EnvConfig(**frappe.conf)

@frappe.whitelist()
def get_env_config():
    try:
        config = validateConfig()
    except Exception as e:
        return {
            "isValid": False,
            "error": f"Invalid config: {str(e)}"
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
