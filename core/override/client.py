# Copyright (c) 2026, core and contributors
# Retry wrapper for frappe.client.set_value on concurrent modification conflicts.

from __future__ import annotations

import json

import frappe
import frappe.model
from frappe import _
from frappe.utils import cint

DEFAULT_MAX_RETRY_COUNT = 1
MAX_ALLOWED_RETRY_COUNT = 5

log = frappe.logger(__name__)


def _parse_values(fieldname: str | dict, value) -> dict:
	if fieldname in (frappe.model.default_fields + frappe.model.child_table_fields):
		frappe.throw(_("Cannot edit standard fields"))

	if not value:
		values = fieldname
		if isinstance(fieldname, str):
			try:
				values = json.loads(fieldname)
			except ValueError:
				values = {fieldname: ""}
	else:
		values = {fieldname: value}

	return values


def _apply_changed_values(doc, values: dict) -> dict:
	changed = {}
	for field, new_value in values.items():
		if doc.get(field) != new_value:
			changed[field] = new_value

	if changed:
		doc.update(changed)

	return changed


def _set_value_once(doctype: str, name: str, fieldname: str | dict, value) -> dict:
	values = _parse_values(fieldname, value)

	if not frappe.get_meta(doctype).istable:
		doc = frappe.get_doc(doctype, name, for_update=True)
		changed = _apply_changed_values(doc, values)
	else:
		row = frappe.db.get_value(doctype, name, ["parenttype", "parent"], as_dict=True)
		doc = frappe.get_doc(row.parenttype, row.parent, for_update=True)
		child = doc.getone({"doctype": doctype, "name": name})
		changed = _apply_changed_values(child, values)

	if changed:
		doc.save()

	return doc.as_dict()


@frappe.whitelist(methods=["POST", "PUT"])
def set_value(
	doctype: str,
	name: str,
	fieldname: str | dict,
	value=None,
	max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
) -> dict:
	"""Set document field values, retrying only on TimestampMismatchError."""
	retries = min(
		MAX_ALLOWED_RETRY_COUNT,
		max(1, cint(max_retry_count) or DEFAULT_MAX_RETRY_COUNT),
	)

	for attempt in range(retries):
		try:
			log.info(f"set_value attempt {attempt + 1}/{retries} for {doctype}/{name}")
			return _set_value_once(doctype, name, fieldname, value)
		except frappe.TimestampMismatchError:
			frappe.db.rollback()
			if attempt == retries - 1:
				raise
			log.info(
				"set_value retry %s/%s for %s/%s",
				attempt + 2,
				retries,
				doctype,
				name,
			)

	raise frappe.TimestampMismatchError
