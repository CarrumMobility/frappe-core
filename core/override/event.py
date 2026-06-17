# Copyright (c) 2026, core and contributors
# Extended Event behaviour for CRM (Callback category → Communication medium).

from __future__ import annotations

from frappe.desk.doctype.event import event as event_module
from frappe.desk.doctype.event.event import Event
from frappe.utils import get_fullname

COMMUNICATION_MAPPING = {
	**event_module.communication_mapping,
	"Callback": "Phone",
	"Visit Date": "Other",
	"PMS": "Other",
	"WS": "Other",
	"Maintenance": "Other",
}


class CustomEvent(Event):
	"""Subclass so Callback events map to a valid Communication medium (see communication_mapping)."""

	def update_communication(self, participant, communication):
		communication.communication_medium = "Event"
		communication.subject = self.subject
		communication.content = self.description if self.description else self.subject
		communication.communication_date = self.starts_on
		communication.sender = self.owner
		communication.sender_full_name = get_fullname(self.owner)
		communication.reference_doctype = self.doctype
		communication.reference_name = self.name
		communication.communication_medium = (
			COMMUNICATION_MAPPING.get(self.event_category) if self.event_category else ""
		)
		communication.status = "Linked"
		communication.add_link(participant.reference_doctype, participant.reference_docname)
		communication.save(ignore_permissions=True)
