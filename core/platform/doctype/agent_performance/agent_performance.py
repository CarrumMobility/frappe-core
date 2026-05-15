# Copyright (c) 2026, core and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AgentPerformance(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		agent_id: DF.Link # done capturing
		agent_name: DF.Data # done capturing
		break_duration: DF.Duration | None # done capturing
		click2call_ring_time: DF.Duration | None # done capturing 
		click2call_talktime_duration: DF.Duration | None # done capturing
		date: DF.Date # done capturing
		dialer_session_duration: DF.Duration | None # done capturing
		dialer_talktime_duration: DF.Duration | None # done capturing
		dispose_duration: DF.Duration | None
		fsd_count: DF.Int
		login_duration: DF.Duration | None # done capturing
		login_idle_duration: DF.Duration | None # done capturing
		psd_count: DF.Int

		total_dialer_connects: DF.Int # done capturing
		total_click2call_attempts: DF.Int # capturing
		total_click2call_connects: DF.Int # capturing

		total_unique_attempts: DF.Int # capturing
		total_unique_connects: DF.Int # capturing

		walkin_count: DF.Int 
		schedules_followup: DF.Int # done capturing
		scheduled_followup: DF.Int # done capturing
		completed_scheduled_followup: DF.Int # done capturing
		dialer_session_count: DF.Int # done capturing
		break_count: DF.Int # done capturing

	# end: auto-generated types
	pass

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	