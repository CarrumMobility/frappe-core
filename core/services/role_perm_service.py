from __future__ import annotations

import logging
import frappe

from core.constants.enums import ReferenceDocType, Roles

PERMISSION_FIELDS = {
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
}

log = frappe.logger("core_services_role_perm_service")
log.setLevel(logging.INFO)

_STARTUP_ENQUEUE_DONE = False


class RolePermService:
	def __init__(self):
		self.role_permissions = {
			"hub_manager": {
				"CRM Lead": ["create", "read", "select", "write"],
				"Call Session": ["create", "read", "select", "write"],
				"Call Log": ["create", "read", "select", "write"],
				"CRM Lead Status": ["create", "read", "select", "write"],
				"FCRM Note": ["create", "read", "select", "write"],
				"FCRM Event": ["create", "read", "select", "write"],
				"FCRM Settings": ["read", "select"],
				"User dialer session logs": ["read", "select"],
				"payment_logs": ["read", "select"],
			}
		}

		self.roles = {
			"hub_manager": {
				"role_name": Roles.HUB_MANAGER,
				"desk_access": 0,
			},
			"telecaller": {
				"role_name": Roles.TELECALLER,
				"desk_access": 0,
			},
			"telecaller_lead": {
				"role_name": Roles.TELECALLER_LEAD,
				"desk_access": 0,
			},
			"onboarding": {
				"role_name": Roles.ONBOARDING,
				"desk_access": 0,
			},
			"driver_manager": {
				"role_name": Roles.DRIVER_MANAGER,
				"desk_access": 0,
			},
		}

	def _normalize_doctype(self, doctype: str) -> str:
		return doctype[3:] if doctype.startswith("tab") else doctype

	def _ensure_role(self, role_name: str, desk_access: int) -> str:
		existing = frappe.db.exists(ReferenceDocType.ROLE, role_name)
		if existing:
			if frappe.db.get_value(ReferenceDocType.ROLE, role_name, "desk_access") != desk_access:
				frappe.db.set_value(ReferenceDocType.ROLE, role_name, "desk_access", desk_access, update_modified=False)
			return role_name

		role_doc = frappe.new_doc(ReferenceDocType.ROLE)
		role_doc.role_name = role_name
		role_doc.desk_access = desk_access
		role_doc.insert(ignore_permissions=True)
		return role_doc.name

	def _ensure_custom_docperm(self, role_name: str, doctype: str, permission_types: list[str]) -> None:
		normalized_doctype = self._normalize_doctype(doctype)

		if not frappe.db.exists("DocType", normalized_doctype):
			log.warning(
				f"[RolePermService] Skipping permissions for missing doctype '{normalized_doctype}' and role '{role_name}'"
			)
			return

		filter_args = {
			"parent": normalized_doctype,
			"role": role_name,
			"permlevel": 0,
			"if_owner": 0,
		}

		custom_docperm_name = frappe.db.get_value(ReferenceDocType.CUSTOM_DOC_PERM, filter_args)
		custom_docperm = (
			frappe.get_doc(ReferenceDocType.CUSTOM_DOC_PERM, custom_docperm_name)
			if custom_docperm_name
			else frappe.get_doc(
				{
					"doctype": ReferenceDocType.CUSTOM_DOC_PERM,
					"parent": normalized_doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role_name,
					"permlevel": 0,
					"if_owner": 0,
				}
			)
		)

		valid_permission_types = {perm for perm in permission_types if perm in PERMISSION_FIELDS}
		invalid_permission_types = sorted(set(permission_types) - valid_permission_types)
		if invalid_permission_types:
			log.warning(
				f"[RolePermService] Ignoring invalid permission(s) {invalid_permission_types} for {normalized_doctype}/{role_name}"
			)

		for perm in PERMISSION_FIELDS:
			custom_docperm.set(perm, 1 if perm in valid_permission_types else 0)

		custom_docperm.save(ignore_permissions=True)

	def create_roles_and_permissions(self):
		log.info("WORKER: creating roles and permissions")
		for role_key, role_data in self.roles.items():
			role_name = role_data["role_name"]
			self._ensure_role(role_name=role_name, desk_access=role_data.get("desk_access", 0))

			role_permission_map = self.role_permissions.get(role_key, {})
			for doctype, permissions in role_permission_map.items():
				self._ensure_custom_docperm(
					role_name=role_name,
					doctype=doctype,
					permission_types=permissions,
				)

		frappe.clear_cache()

	def enqueue_role_n_role_permission_creation(self):
		log.info("Enqueuing role and permission sync job")
		frappe.enqueue(
			method="core.services.role_perm_service.handle_create_role_n_permission",
			queue="default",
			job_id="core.role_perm.sync",
			deduplicate=True,
		)


_role_perm_service = RolePermService()


def enqueue_role_n_role_permission_creation():
	_role_perm_service.enqueue_role_n_role_permission_creation()


def enqueue_role_n_role_permission_creation_on_migration():
	print("Enqueuing role n role permission creation on migration")
	_role_perm_service.enqueue_role_n_role_permission_creation()


def handle_create_role_n_permission():
	_role_perm_service.create_roles_and_permissions()