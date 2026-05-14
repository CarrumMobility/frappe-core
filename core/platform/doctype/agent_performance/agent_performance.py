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

		agent_id: DF.Link
		agent_name: DF.Data
		break_duration: DF.Duration | None
		click2call_ring_time: DF.Duration | None
		click2call_talktime_duration: DF.Duration | None
		date: DF.Date
		dialer_ring_duration: DF.Duration | None
		dialer_session_browser_mismatch_duration: DF.Duration | None
		dialer_session_duration: DF.Duration | None
		dialer_talktime_duration: DF.Duration | None
		dispose_duration: DF.Duration | None
		fsd_count: DF.Int
		login_duration: DF.Duration | None
		login_idle_duration: DF.Duration | None
		psd_count: DF.Int
		total_dialer_connects: DF.Int
		total_mannual_attempts: DF.Int
		total_mannual_connects: DF.Int
		walkin_count: DF.Int
	# end: auto-generated types
	pass

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	