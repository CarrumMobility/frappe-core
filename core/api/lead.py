from datetime import date, datetime
from typing import Optional
from uuid import UUID

import frappe
from frappe import _
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from core.api import carrum_drivers
from core.constants.enums import EnumValues
from core.services.crm_lead.lead_service import LeadService

logger = frappe.logger("core.api.lead")

lead_service = LeadService()

_EMPTY = (None, "")

# Carrum portal fields forwarded to ``update_driver`` (may also exist on CRM Lead).
PORTAL_LEAD_UPDATE_FIELDS = frozenset(
	{
		"scheme_id",
		"scheme_type",
		"old_scheme_name",
		"tenure",
		"emi_id",
		"remove_emi",
		"uber_id",
	}
)


class UpdateLeadDtoSchema(BaseModel):
	"""Partial update payload for ``update_lead``. Only set fields are applied."""

	model_config = ConfigDict(extra="forbid")

	lead_name: Optional[str] = None
	mobile_no: Optional[str] = None
	email: Optional[str] = None
	gender: Optional[str] = None
	alternate_phone: Optional[str] = None
	preferred_lang: Optional[str] = None

	lead_type: Optional[str] = None
	primary_status: Optional[str] = None
	secondary_status: Optional[str] = None
	status: Optional[str] = None
	hub_visit_status: Optional[str] = None
	uber_id_status: Optional[str] = None
	uber_id: Optional[UUID] = None
	driving_license_status: Optional[str] = None

	hub_id: Optional[str] = None
	custom_hub_name: Optional[str] = None
	telecaller: Optional[str] = None
	driver_manager: Optional[str] = None
	primary_lead: Optional[str] = None
	source: Optional[str] = None
	source_id: Optional[str] = None
	user_tags: Optional[str] = None

	aadhar_no: Optional[str] = None
	pancard_number: Optional[str] = None
	driving_license_number: Optional[str] = None
	driving_license_issue_date: Optional[date] = None
	driving_license_expiry_date: Optional[date] = None
	uber_rating: Optional[str] = None

	address: Optional[str] = None
	current_address_line1: Optional[str] = None
	current_address_line2: Optional[str] = None
	current_city: Optional[str] = None
	current_state: Optional[str] = None
	current_country: Optional[str] = None
	current_pincode: Optional[str] = None
	current_landmark: Optional[str] = None
	current_address_number: Optional[str] = None
	current_address_proof_type: Optional[str] = None
	location_link: Optional[str] = None

	bank_account_number: Optional[str] = None
	bank_ifsc: Optional[str] = None

	aadhaar_card_front: Optional[str] = None
	aadhaar_card_back: Optional[str] = None
	driving_license_front: Optional[str] = None
	driving_license_back: Optional[str] = None
	driver_partner_selfie: Optional[str] = None
	pancard_pic: Optional[str] = None
	bank_passbook_pic: Optional[str] = None
	current_address_proof: Optional[str] = None
	image: Optional[str] = None

	business_type_id: Optional[str] = None
	business_type_name: Optional[str] = None
	car_type_id: Optional[str] = None
	scheme_id: Optional[str | int] = None
	scheme_name: Optional[str] = None
	referral_scheme_id: Optional[str] = None
	preferred_business_type_1: Optional[str] = None
	preferred_scheme_1: Optional[str] = None
	preferred_business_type_2: Optional[str] = None
	preferred_scheme_2: Optional[str] = None
	scheme_type: Optional[str] = None
	old_scheme_name: Optional[str] = None
	tenure: Optional[int] = None
	emi_id: Optional[str] = None
	remove_emi: Optional[bool] = None

	gate_ticket_no: Optional[str] = None
	hubvisit_category: Optional[str] = None
	hubvisit_subcategory: Optional[str] = None

	@field_validator("*", mode="before")
	@classmethod
	def _blank_to_none(cls, v):
		if v == "":
			return None
		return v

	@field_validator(
		"scheme_type",
		"old_scheme_name",
		"lead_name",
		"email",
		"mobile_no",
		mode="before",
	)
	@classmethod
	def _strip_str_field(cls, v):
		if v in _EMPTY:
			return None
		return str(v).strip() or None

	@field_validator("tenure", mode="before")
	@classmethod
	def _validate_tenure(cls, v):
		if v in _EMPTY:
			return None
		val = int(v)
		if val < 1:
			raise ValueError(_("Tenure must be greater than 0"))
		return val

	@field_validator("uber_id", mode="before")
	@classmethod
	def _normalize_uber_id(cls, v):
		if v in _EMPTY:
			return None
		if isinstance(v, UUID):
			return v
		s = str(v).strip()
		if not s:
			return None
		try:
			return UUID(s)
		except ValueError:
			raise ValueError(_("Uber ID must be a valid UUID"))

	@field_validator("lead_type")
	@classmethod
	def _validate_lead_type(cls, v):
		if v is None:
			return v
		allowed = {"DRIVER", "LEAD", "VENDOR"}
		if v not in allowed:
			raise ValueError(_("lead_type must be one of {0}").format(", ".join(sorted(allowed))))
		return v

	@field_validator("hub_visit_status")
	@classmethod
	def _validate_hub_visit_status(cls, v):
		if v is None:
			return v
		allowed = {"NOT_IN_HUB", "IN_HUB", "HUB_VISITED"}
		if v not in allowed:
			raise ValueError(_("hub_visit_status must be one of {0}").format(", ".join(sorted(allowed))))
		return v

	@model_validator(mode="after")
	def _validate_tenure_emi_pair(self):
		if ("tenure" in self.model_fields_set or "emi_id" in self.model_fields_set) and (
			self.tenure is None
		) != (self.emi_id is None):
			raise ValueError(_("tenure and emi_id must be provided together"))
		return self

	def split_destinations(self) -> tuple[dict, dict]:
		"""Return ``(erp_updates, portal_updates)`` for fields that were actually set."""
		dump = self.model_dump(exclude_unset=True)
		portal_updates = {k: v for k, v in dump.items() if k in PORTAL_LEAD_UPDATE_FIELDS}
		if "uber_id" in portal_updates and portal_updates["uber_id"] is not None:
			portal_updates["uber_id"] = str(portal_updates["uber_id"])
		# "scheme_id" also lives on the CRM Lead doc, so it is dual-written; "uber_id" is
		# portal-only (no such field on CRM Lead) and must not be forwarded to lead.set().
		erp_updates = {k: v for k, v in dump.items() if k not in PORTAL_LEAD_UPDATE_FIELDS or k == "scheme_id"}
		# portal-only keys must not be written onto the CRM Lead doc
		for key in ("scheme_type", "old_scheme_name", "tenure", "emi_id", "remove_emi"):
			erp_updates.pop(key, None)
		return erp_updates, portal_updates


def _format_update_lead_validation_errors(exc: ValidationError) -> str:
	parts = []
	for err in exc.errors():
		loc = err.get("loc") or ()
		field = loc[-1] if loc else "updates"
		msg = err.get("msg", "")
		parts.append(f"{field}: {msg}")
	return "; ".join(parts) or str(exc)


def _parse_update_lead_payload(data) -> UpdateLeadDtoSchema:
	if data is None:
		frappe.throw(_("updates is required"), frappe.ValidationError)
	if isinstance(data, UpdateLeadDtoSchema):
		return data
	if isinstance(data, dict):
		if not data:
			frappe.throw(_("updates is required"), frappe.ValidationError)
		try:
			return UpdateLeadDtoSchema.model_validate(data)
		except ValidationError as e:
			frappe.throw(_format_update_lead_validation_errors(e), frappe.ValidationError)
	if isinstance(data, str):
		raw = data.strip()
		if not raw:
			frappe.throw(_("updates is required"), frappe.ValidationError)
		try:
			return UpdateLeadDtoSchema.model_validate_json(raw)
		except ValidationError as e:
			frappe.throw(_format_update_lead_validation_errors(e), frappe.ValidationError)
	frappe.throw(_("updates must be a JSON object"), frappe.ValidationError)
	raise AssertionError("unreachable")


@frappe.whitelist(methods=['POST'])
def find_or_create_lead(
	mobile_no: str,
	upload_source: str ,
	name: str | None = None,
	source: str | None = None ,
	source_id: str | None = None,
	hub_id: str | None = None,
	hub_name: str | None = None,
):
	logger.info(
		"find_or_create_lead: mobile_no=%s source=%s source_id=%s upload_source=%s hub_id=%s",
		mobile_no,
		source,
		source_id,
		upload_source,
		hub_id,
	)
	lead = lead_service.find_or_create_lead(
		mobile_no=mobile_no,
		source=source,
		source_id=source_id,
		allow_source_update=False,
		other_info={
			"lead_name": name,
			"upload_source": upload_source,
			"hub_id": hub_id,
			"hub_name": hub_name
		},
	)
	if lead is None:
		logger.error("find_or_create_lead: unable to find or create lead for mobile_no=%s", mobile_no)
		frappe.throw(_("Unable to find or create lead"), frappe.ValidationError)

	logger.info("find_or_create_lead done: lead=%s", lead.name)

	return {
		"lead": lead.as_dict(),
	}


@frappe.whitelist()
def update_lead(lead_id: str, updates: dict, lsq_id: str | None = None):
	logger.info("update_lead: lead=%s fields=%s lsq_id=%s", lead_id, list(updates or {}), lsq_id)
	payload = _parse_update_lead_payload(updates)
	lead_updates, portal_updates = payload.split_destinations()

	lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_id)
	erp_db_changed = False

	for field, value in lead_updates.items():
		lead.set(field, value)
		erp_db_changed = True

	if erp_db_changed:
		lead.save(ignore_permissions=True)

	portal_result = None
	if portal_updates:
		account_id = (lead.custom_account_id or "").strip()
		if account_id:
			portal_result = carrum_drivers.update_driver(account_id, portal_updates)
		else:
			logger.warning(
				"update_lead: portal_db fields requested (%s) but lead %s has no custom_account_id — skipped",
				list(portal_updates),
				lead_id,
			)

	logger.info(
		"update_lead done: lead=%s erp_fields=%s portal_fields=%s lsq_id=%s",
		lead_id,
		list(lead_updates),
		list(portal_updates),
		lsq_id,
	)
	return {
		"is_valid": True,
		"data": {
			"lead": lead.as_dict(),
			"lead_updates": lead_updates,
			"portal_updates": portal_updates or None,
			"portal_result": portal_result,
			"_debug": (portal_result or {}).get("_debug"),
		},
	}


@frappe.whitelist()
def get_lead(lead_id: str, lsq_id: str | None = None):
	logger.info("Getting lead %s (lsq_id=%s)", lead_id, lsq_id)
	lead = frappe.get_doc(EnumValues.ReferenceDocType.CRM_LEAD, lead_id)

	lead_type= lead.get("lead_type")
	portal_details = None
	if lead_type == EnumValues.LeadType.DRIVER:
		portal_details = carrum_drivers.get_portal_driver_detail(lead.name)
		portal_details = portal_details.get("data", {}).get("results", {})

	return {
		"is_valid": True,
		"data": {
			"lead_details": lead.as_dict(),
			"portal_details": portal_details
		}
	}
