# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_duration


class CallSession(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		agent: DF.Link | None
		agent_answer_event_id: DF.Data | None
		agent_answer_event_log: DF.JSON | None
		agent_answered_at: DF.Datetime | None
		agent_call_id: DF.Data | None
		calling_method: DF.Literal["", "Dialer", "Click2Call"]
		direction: DF.Literal["", "INBOUND", "OUTBOUND"]
		disposed_at: DF.Datetime | None
		disposition_event_id: DF.Data | None
		disposition_raw: DF.JSON | None
		disposition_remarks: DF.SmallText | None
		disposition_status: DF.Data | None
		disposition_timing: DF.Literal["","IMMEDIATE", "LATE"]
		duration: DF.Duration | None
		failure_reason: DF.Text | None
		hangup_at: DF.Datetime | None
		hangup_by: DF.Literal["","LEAD", "AGENT", "SYSTEM"]
		hangup_event_id: DF.Data | None
		hangup_event_log: DF.JSON | None
		hangup_reason: DF.Data | None
		is_visit_scheduled: DF.Check
		lead: DF.Link
		lead_answer_event_id: DF.Data | None
		lead_answer_event_log: DF.JSON | None
		lead_answered_at: DF.Datetime | None
		lead_phone: DF.Data
		scheduled_visit_date: DF.Date | None
		status: DF.Literal["INITIATED", "FAILED", "AGENT_CONNECTED", "CUSTOMER_CONNECTED", "MISSED", "DISCONNECTED", "DISPOSED"]
		sub_disposition_status: DF.Data | None
		vendor_agent_id: DF.Data | None
		vendor_name: DF.Literal["", "Smartflo", "Girnar"]
	# end: auto-generated types

	@staticmethod
	def default_list_data():
		columns = [
			{
				"label": _("Name"),
				"type": "Data",
				"key": "name",
				"width": "12rem",
			},
			{
				"label": _("Calling method"),
				"type": "Select",
				"key": "calling_method",
				"width": "8rem",
			},
			{
				"label": _("Lead"),
				"type": "Link",
				"key": "lead",
				"options": "CRM Lead",
				"width": "12rem",
			},
			{
				"label": _("Direction"),
				"type": "Select",
				"key": "direction",
				"width": "8rem",
			},
			{
				"label": _("Status"),
				"type": "Select",
				"key": "status",
				"width": "10rem",
			},
			{
				"label": _("Agent"),
				"type": "Link",
				"key": "agent",
				"options": "User",
				"width": "10rem",
			},
			{
				"label": _("Failure reason"),
				"type": "Text",
				"key": "failure_reason",
				"width": "16rem",
			},
			{
				"label": _("Hangup by"),
				"type": "Select",
				"key": "hangup_by",
				"width": "8rem",
			},
			{
				"label": _("Call at"),
				"type": "Datetime",
				"key": "agent_answered_at",
				"width": "10rem",
			},
			{
				"label": _("Disposition timing"),
				"type": "Select",
				"key": "disposition_timing",
				"width": "10rem",
			},
			{
				"label": _("Duration"),
				"type": "Duration",
				"key": "duration",
				"width": "8rem",
			},
		]
		rows = [
			"name",
			"calling_method",
			"lead",
			"direction",
			"status",
			"agent",
			"failure_reason",
			"hangup_by",
			"agent_answered_at",
			"disposition_timing",
			"duration",
			"disposition_status",
			"disposition_remarks",
			"lead_phone",
			"modified",
		]
		return {"columns": columns, "rows": rows}

	@staticmethod
	def parse_list_data(rows):
		if not rows:
			return rows
		lead_ids = {r.get("lead") for r in rows if r.get("lead")}
		lead_names = {}
		lead_hubs = {}
		if lead_ids:
			lead_fields = ["name", "lead_name"]
			if frappe.db.has_column("CRM Lead", "custom_hub_name"):
				lead_fields.append("custom_hub_name")
			for d in frappe.get_all(
				"CRM Lead",
				filters={"name": ("in", list(lead_ids))},
				fields=lead_fields,
			):
				lead_names[d.name] = d.lead_name or d.name
				if "custom_hub_name" in d:
					lead_hubs[d.name] = d.custom_hub_name or ""
		user_ids = {r.get("agent") for r in rows if r.get("agent")}
		user_names = {}
		if user_ids:
			for d in frappe.get_all(
				"User",
				filters={"name": ("in", list(user_ids))},
				fields=["name", "full_name"],
			):
				user_names[d.name] = d.full_name or d.name
		for r in rows:
			lid = r.get("lead")
			r["_lead_name"] = lead_names.get(lid) or lid
			r["_hub_name"] = lead_hubs.get(lid) or ""
			r["_direction_label"] = r.get("direction") or ""
			aid = r.get("agent")
			if aid:
				r["_agent"] = {"label": user_names.get(aid) or aid, "image": None}
			dur = r.get("duration")
			if dur is not None:
				try:
					sec = float(dur)
					r["_duration"] = format_duration(sec) if sec else ""
				except (TypeError, ValueError):
					r["_duration"] = ""
			else:
				r["_duration"] = ""
		return rows
