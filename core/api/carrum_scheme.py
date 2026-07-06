from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
from core.services.carrum_client import old_carrum_client


def _extract_alias_results(data):
	if not data or not isinstance(data, dict):
		return []
	if isinstance(data.get("results"), list):
		return data["results"]
	inner = data.get("data")
	if isinstance(inner, dict) and isinstance(inner.get("results"), list):
		return inner["results"]
	return []


def _row_stored_scheme_id(row):
	return str(row.get("id") or "").strip()


def _row_portal_scheme_id(row):
	return str(row.get("scheme_id") or row.get("schemeId") or "").strip()


def _row_matches_stored_scheme_id(row, scheme: str) -> bool:
	stored = _row_stored_scheme_id(row)
	if stored and stored == scheme:
		return True
	return _row_portal_scheme_id(row) == scheme


def _row_scheme_id(row):
	"""Backward-compatible alias for stored scheme id on alias rows."""
	return _row_stored_scheme_id(row) or _row_portal_scheme_id(row)


def _is_hub_agnostic_alias_row(row):
	return not str(row.get("hub_id") or row.get("hubId") or "").strip() and not str(
		row.get("hub_name") or row.get("hubName") or ""
	).strip()


def _row_car_type_id(row):
	return str(
		row.get("car_type_id")
		or row.get("scheme_car_type_id")
		or row.get("schemeCarTypeId")
		or ""
	).strip()


def _filter_alias_rows_for_hub(results, hub_id):
	hub = str(hub_id or "").strip()
	if not hub or not results:
		return []
	filtered = [
		row
		for row in results
		if _is_hub_agnostic_alias_row(row)
		or str(row.get("hub_id") or row.get("hubId") or "").strip() == hub
	]
	return filtered or list(results)


def scheme_requires_car_type_for_hub(hub_id, scheme_id):
	"""True when Carrum alias rows for ``scheme_id`` expose at least one car type."""
	scheme = str(scheme_id or "").strip()
	hub = str(hub_id or "").strip()
	if not scheme or not hub:
		return True
	try:
		client = old_carrum_client(timeout=30)
		result = client.request(
			method="GET",
			path="/api/v1/scheme/alias",
			params={"hub_id": hub},
			log_tag="scheme-requires-car-type",
		)
		payload = result.get("data") if result.get("success") else {}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "scheme_requires_car_type_for_hub")
		return True
	rows = _filter_alias_rows_for_hub(_extract_alias_results(payload), hub)
	for row in rows:
		if not _row_matches_stored_scheme_id(row, scheme):
			continue
		if _row_car_type_id(row):
			return True
	return False


@frappe.whitelist()
def get_scheme_list():
	payload = frappe.request.get_json() or {}
	business_type_id = str(
		payload.get("businessTypeId") or payload.get("business_type_id") or ""
	).strip()

	if not business_type_id:
		return {
			"success": False,
		}

	client = old_carrum_client(timeout=30)
	result = client.request(
		method="GET",
		path="/api/v1/scheme/alias",
		params={"hub_id": business_type_id},
		log_tag="get-scheme-list",
	)
	if not result.get("success"):
		return {
			"success": False,
			"error": result.get("error"),
		}
	return {
		"success": True,
		"data": result.get("data"),
		"request_url": result.get("request_url"),
	}
