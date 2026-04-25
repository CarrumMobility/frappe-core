import frappe
from frappe.utils import cint, flt


def _persist_api_hit(
	api_name,
	end_point,
	request_payload,
	response,
	status_code,
	error_message,
	execution_time,
	created_by=None,
):
	"""Background job: create Api hit log (called via frappe.enqueue)."""
	doc = frappe.get_doc(
		{
			"doctype": "Api hit log",
			"api_name": api_name,
			"end_point": end_point,
			"request_payload": request_payload,
			"response": response,
			"status_code": cint(status_code or 0),
			"error_message": (error_message or None),
			"execution_time": flt(execution_time or 0, 4),
		}
	)
	if created_by and created_by not in (None, "Guest") and frappe.db.exists("User", created_by):
		doc.created_by = created_by
	doc.insert(ignore_permissions=True)


class ApiHitService:
	def __init__(self):
		pass

	def enqueue_log_api_hit(
		self,
		api_name,
		end_point,
		request_payload,
		response,
		status_code,
		error_message,
		execution_time,
		created_by=None,
	):
		frappe.enqueue(
			"core.services.apihit_service._persist_api_hit",
			queue="default",
			api_name=api_name,
			end_point=end_point,
			request_payload=request_payload,
			response=response,
			status_code=status_code,
			error_message=error_message,
			execution_time=execution_time,
			created_by=created_by,
		)

	def log_api_hit(
		self,
		api_name,
		end_point,
		request_payload,
		response,
		status_code,
		error_message,
		execution_time,
		created_by=None,
	):
		"""Synchronous write (e.g. tests or forced sync)."""
		_persist_api_hit(
			api_name,
			end_point,
			request_payload,
			response,
			status_code,
			error_message,
			execution_time,
			created_by=created_by,
		)


api_hit_service = ApiHitService()
