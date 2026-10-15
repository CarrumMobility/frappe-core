"""Business events (for example CrmLeadViewed).

One OpenTelemetry log record per event, exported to Loki with ``event.name``
and the attributes as structured metadata, linked to the current trace.
Query in Grafana with ``{service_name="erpnext"} | event_name="CrmLeadViewed"``.

The record is emitted through the OpenTelemetry Logs API directly rather than
a Python logger, so FRAPPE_LOG_LEVEL (WARNING in deployed environments)
cannot filter events out.
"""

from __future__ import annotations

import json
import logging
import os

import frappe

_LOG = logging.getLogger(__name__)


def record_event(event_type: str, attributes: dict | None = None) -> None:
	if os.environ.get("OBSERVABILITY", "otel").lower() == "off":
		return

	try:
		from opentelemetry._logs import LogRecord, SeverityNumber, get_logger

		params: dict = {"event.name": event_type}
		site = getattr(frappe.local, "site", None)
		if site:
			params["frappe.site"] = site
		for key, value in (attributes or {}).items():
			if value is None:
				continue
			if isinstance(value, (dict, list, tuple)):
				value = json.dumps(value, default=str)
			params[key] = value

		get_logger("core.events").emit(
			LogRecord(
				body=event_type,
				severity_number=SeverityNumber.INFO,
				severity_text="INFO",
				attributes=params,
			)
		)
	except Exception:
		_LOG.warning("Failed to record event %s", event_type, exc_info=True)
