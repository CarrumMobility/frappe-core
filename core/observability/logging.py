"""Make Python log records safe for log export.

Log exporters read ``record.msg``. That leaves the exported message empty or
unreadable when:

- Frappe passes a dict as the log message (e.g. ``log_request()``).
- The message uses %-formatting and args are still on the record.

This module materializes the final string on ``record.msg`` at record creation.
"""

from __future__ import annotations

import json
import logging

_installed = False
_original_record_factory = None


def _format_request_dict(d: dict) -> str:
	method = d.get("method", "")
	path = d.get("full_path", d.get("base_url", ""))
	status = d.get("http_status_code", "")
	user = d.get("user", "")
	request_body = d.get("request_body")

	parts = []
	if method and path:
		parts.append(f"{method} {path}")
	if status:
		parts.append(f"→ {status}")
	if user:
		parts.append(f"user={user}")
	if request_body is not None:
		parts.append(f"request_body={json.dumps(request_body, default=str)}")
	return " ".join(parts) if parts else json.dumps(d, default=str)


def _format_dict_message(d: dict) -> str:
	if "full_path" in d or "method" in d:
		return _format_request_dict(d)
	return json.dumps(d, default=str)


def _record_factory(*args, **kwargs):
	record = _original_record_factory(*args, **kwargs)

	if isinstance(record.msg, dict):
		record.msg = _format_dict_message(record.msg)
		record.args = None
	elif record.args:
		try:
			record.msg = record.getMessage()
		except Exception:
			record.msg = str(record.msg)
		record.args = None

	return record


def install_log_compat() -> None:
	"""Install the log record factory once per process (idempotent)."""
	global _installed, _original_record_factory
	if _installed:
		return
	_original_record_factory = logging.getLogRecordFactory()
	logging.setLogRecordFactory(_record_factory)
	_installed = True
