import frappe

from pydantic import BaseModel

# Env config validation schema using pydantic
class EnvConfig(BaseModel):
    master_password: str
    chatwoot_account_id: int
    chatwoot_base_url: str
    carrum_base_url: str
    carrum_token: str

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
