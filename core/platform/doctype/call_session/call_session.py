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
		calling_method: DF.Literal["", "Dialer", "Agent"]
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
		scheduled_visit_date: DF.Datetime | None
		status: DF.Literal["INITIATED", "FAILED", "AGENT_CONNECTED", "CUSTOMER_CONNECTED", "OB Missed", "IB Missed", "DISCONNECTED", "DISPOSED"]
		sub_disposition_status: DF.Data | None
		vendor_agent_id: DF.Data | None
		vendor_name: DF.Literal["", "Smartflo", "Girnar"]
		lead_source_during_call: DF.Data | None
		recording_url: DF.LongText | None
		campaign_name: DF.Data | None
		campaign_id: DF.Data | None
		lead_callback_datetime: DF.Datetime | None
		ring_duration: DF.Duration | None
	# end: auto-generated types

	def validate(self) -> None:
		self._validate_agent_call_id_immutable()

	def _validate_agent_call_id_immutable(self) -> None:
		"""``agent_call_id`` is set once from telephony webhooks and must not be edited."""
		current = (self.agent_call_id or "").strip()
		if not current or self.is_new():
			return
		previous = frappe.db.get_value(self.doctype, self.name, "agent_call_id")
		if (previous or "").strip() and (previous or "").strip() != current:
			frappe.throw(
				_("Agent call id cannot be changed once set."),
				frappe.ValidationError,
				title=_("Agent call id locked"),
			)

	@staticmethod
	def default_list_data():
		columns = [
			{
				"label": _("Lead ID"),
				"type": "Link",
				"key": "lead",
				"options": "CRM Lead",
				"width": "12rem",
			},
			{
				"label": _("Call status"),
				"type": "Select",
				"key": "status",
				"width": "10rem",
			},
			{
				"label": _("Call direction"),
				"type": "Select",
				"key": "direction",
				"width": "9rem",
			},
			{
				"label": _("Primary status"),
				"type": "Data",
				"key": "disposition_status",
				"width": "11rem",
			},
			{
				"label": _("Secondary status"),
				"type": "Data",
				"key": "sub_disposition_status",
				"width": "14rem",
			},
			{
				"label": _("Duration"),
				"type": "Duration",
				"key": "duration",
				"width": "8rem",
			},
			{
				"label": _("Caller Type"),
				"type": "Select",
				"key": "calling_method",
				"width": "9rem",
			},
			{
				"label": _("Agent"),
				"type": "Link",
				"key": "agent",
				"options": "User",
				"width": "10rem",
			},
			{
				"label": _("Next followup date"),
				"type": "Datetime",
				"key": "lead_callback_datetime",
				"width": "12rem",
			},
			{
				"label": _("Next Visit Date"),
				"type": "Datetime",
				"key": "scheduled_visit_date",
				"width": "12rem",
			},
			{
				"label": _("Disposition remarks"),
				"type": "Small Text",
				"key": "disposition_remarks",
				"width": "14rem",
			},
			{
				"label": _("Campaign Id"),
				"type": "Data",
				"key": "campaign_id",
				"width": "10rem",
			},
			{
				"label": _("Campaign Name"),
				"type": "Data",
				"key": "campaign_name",
				"width": "11rem",
			},
			{
				"label": _("Failure Reason"),
				"type": "Text",
				"key": "failure_reason",
				"width": "12rem",
			},
			{
				"label": _("Ring duration"),
				"type": "Duration",
				"key": "ring_duration",
				"width": "9rem",
			},
			{
				"label": _("Created At"),
				"type": "Datetime",
				"key": "creation",
				"width": "10rem",
			},
			{
				"label": _("Agent answered at"),
				"type": "Datetime",
				"key": "agent_answered_at",
				"width": "11rem",
			},
			{
				"label": _("Lead answer at"),
				"type": "Datetime",
				"key": "lead_answered_at",
				"width": "11rem",
			},
			{
				"label": _("Hangup At"),
				"type": "Datetime",
				"key": "hangup_at",
				"width": "11rem",
			},
			{
				"label": _("Hangup By"),
				"type": "Select",
				"key": "hangup_by",
				"width": "9rem",
			},
			{
				"label": _("Hangup Reason"),
				"type": "Data",
				"key": "hangup_reason",
				"width": "12rem",
			},
			{
				"label": _("Dispose At"),
				"type": "Datetime",
				"key": "disposed_at",
				"width": "11rem",
			},
			{
				"label": _("Recording"),
				"type": "Long Text",
				"key": "recording_url",
				"width": "10rem",
			},
		]
		rows = [
			"lead",
			"status",
			"direction",
			"disposition_status",
			"sub_disposition_status",
			"duration",
			"calling_method",
			"agent",
			"lead_callback_datetime",
			"scheduled_visit_date",
			"disposition_remarks",
			"campaign_id",
			"campaign_name",
			"failure_reason",
			"ring_duration",
			"creation",
			"agent_answered_at",
			"lead_answered_at",
			"hangup_at",
			"hangup_by",
			"hangup_reason",
			"disposed_at",
			"recording_url",
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
			ring_dur = r.get("ring_duration")
			if ring_dur is not None:
				try:
					sec = float(ring_dur)
					r["_ring_duration"] = format_duration(sec) if sec else ""
				except (TypeError, ValueError):
					r["_ring_duration"] = ""
			else:
				r["_ring_duration"] = ""
		return rows
