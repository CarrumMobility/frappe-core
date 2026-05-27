from __future__ import annotations

import logging

import frappe
from frappe.utils import cint

from core.constants.enums import EnumValues

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

CRM_AGENT_PERMISSIONS = {
	"CRM Lead": ["create", "read", "select", "write"],
	"Call Session": ["create", "read", "select", "write"],
	"Call Log": ["create", "read", "select", "write"],
	"CRM Lead Status": ["create", "read", "select", "write"],
	"FCRM Note": ["create", "read", "select", "write"],
	"FCRM Event": ["create", "read", "select", "write"],
	"FCRM Settings": ["read", "select"],
	"User dialer session logs": ["read", "select", "write", "create", "delete"],
	"User dialer session break logs": ["read", "select", "write", "create", "delete"],
	"payment_logs": ["read", "select"],
	"Lead walkin done": ["create", "read", "select", "write"],
}

# Permissions merged on top of ``TEMPLATE_ROLE_NAME`` (union per doctype).
ADDITIONAL_PERMISSIONS_BY_ROLE: dict[str, dict[str, list[str]]] = {
	"Hub Manager": CRM_AGENT_PERMISSIONS,
	"telecaller": CRM_AGENT_PERMISSIONS,
	"telecaller_lead": CRM_AGENT_PERMISSIONS,
	"onboarding": CRM_AGENT_PERMISSIONS,
	"Driver Manager": CRM_AGENT_PERMISSIONS,
	"Admin": CRM_AGENT_PERMISSIONS,
}

TEMPLATE_ROLE_NAME = "Sales User"

log = frappe.logger("core_services_role_perm_service")
log.setLevel(logging.INFO)

_STARTUP_ENQUEUE_DONE = False


class RolePermService:
	def __init__(self):
		self.roles = {
			"Hub Manager": {
				"role_name": EnumValues.Roles.HUB_MANAGER,
				"desk_access": 0,
			},
			"telecaller": {
				"role_name": EnumValues.Roles.TELECALLER,
				"desk_access": 0,
			},
			"telecaller_lead": {
				"role_name": EnumValues.Roles.TELECALLER_LEAD,
				"desk_access": 0,
			},
			"onboarding": {
				"role_name": EnumValues.Roles.ONBOARDING,
				"desk_access": 0,
			},
			"Driver Manager": {
				"role_name": EnumValues.Roles.DRIVER_MANAGER,
				"desk_access": 0,
			},
		}
		self._sales_user_perm_cache: dict[str, set[str]] | None = None

	def _normalize_doctype(self, doctype: str) -> str:
		return doctype[3:] if doctype.startswith("tab") else doctype

	def _load_sales_user_permission_map(self) -> dict[str, set[str]]:
		if self._sales_user_perm_cache is not None:
			return self._sales_user_perm_cache

		perm_field_list = sorted(PERMISSION_FIELDS)
		by_parent: dict[str, set[str]] = {}

		for table in ("DocPerm", "Custom DocPerm"):
			filters: dict = {"role": TEMPLATE_ROLE_NAME, "permlevel": 0, "if_owner": 0}
			if table == "Custom DocPerm" and frappe.db.has_column("Custom DocPerm", "docstatus"):
				filters["docstatus"] = 0
			rows = frappe.get_all(table, filters=filters, fields=["parent", *perm_field_list])
			for row in rows:
				parent = self._normalize_doctype(row["parent"])
				active = {p for p in PERMISSION_FIELDS if row.get(p)}
				if not active:
					continue
				by_parent.setdefault(parent, set()).update(active)

		self._sales_user_perm_cache = by_parent
		return by_parent

	def _merged_permission_map_for_role(self, role_key: str) -> dict[str, set[str]]:
		self._load_sales_user_permission_map()
		sales = self._sales_user_perm_cache or {}
		merged: dict[str, set[str]] = {dt: set(perms) for dt, perms in sales.items()}
		for doctype, perm_list in ADDITIONAL_PERMISSIONS_BY_ROLE.get(role_key, {}).items():
			ndt = self._normalize_doctype(doctype)
			merged.setdefault(ndt, set()).update(p for p in perm_list if p in PERMISSION_FIELDS)
		return merged

	def _ensure_role(self, role_name: str, desk_access: int) -> str:
		existing = frappe.db.exists(EnumValues.ReferenceDocType.ROLE, role_name)
		if existing:
			if frappe.db.get_value(EnumValues.ReferenceDocType.ROLE, role_name, "desk_access") != desk_access:
				frappe.db.set_value(EnumValues.ReferenceDocType.ROLE, role_name, "desk_access", desk_access, update_modified=False)
			return role_name

		role_doc = frappe.new_doc(EnumValues.ReferenceDocType.ROLE)
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

		custom_docperm_name = frappe.db.get_value(EnumValues.ReferenceDocType.CUSTOM_DOC_PERM, filter_args)
		custom_docperm = (
			frappe.get_doc(EnumValues.ReferenceDocType.CUSTOM_DOC_PERM, custom_docperm_name)
			if custom_docperm_name
			else frappe.get_doc(
				{
					"doctype": EnumValues.ReferenceDocType.CUSTOM_DOC_PERM,
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

		if custom_docperm_name:
			unchanged = all(
				cint(custom_docperm.get(perm)) == (1 if perm in valid_permission_types else 0)
				for perm in PERMISSION_FIELDS
			)
			if unchanged:
				return

		for perm in PERMISSION_FIELDS:
			custom_docperm.set(perm, 1 if perm in valid_permission_types else 0)

		custom_docperm.save(ignore_permissions=True)

	def create_roles_and_permissions(self):
		log.info("WORKER: creating roles and permissions")
		self._sales_user_perm_cache = None
		self._load_sales_user_permission_map()
		if not self._sales_user_perm_cache:
			log.warning(
				f"[RolePermService] No DocPerm/Custom DocPerm rows found for template role '{TEMPLATE_ROLE_NAME}'"
			)

		for role_key, role_data in self.roles.items():
			role_name = role_data["role_name"]
			self._ensure_role(role_name=role_name, desk_access=role_data.get("desk_access", 0))

			merged = self._merged_permission_map_for_role(role_key)
			if not merged:
				log.warning(f"[RolePermService] No merged permissions for role '{role_name}', skipping DocPerm sync")
				continue
			for doctype, perm_set in sorted(merged.items()):
				if not perm_set:
					continue
				self._ensure_custom_docperm(
					role_name=role_name,
					doctype=doctype,
					permission_types=sorted(perm_set),
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