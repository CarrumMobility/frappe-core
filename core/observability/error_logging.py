"""Emit full exception details to Python logs for New Relic log forwarding.

Frappe's default ``log_error_snapshot`` only logs the fixed string
``"New Exception collected in error log"``; the traceback is stored in the
Error Log doctype but never reaches application logs. This module patches
Frappe's error helpers so NR Logs receive the complete exception message and
stack trace (linked to the same APM trace via log correlation).
"""

from __future__ import annotations

import logging
from typing import Any

import frappe

_installed = False
_original_log_error = None

_EXCLUDE_EXCEPTIONS = None
_is_ldap_exception = None


def _error_logger() -> logging.Logger:
	return frappe.logger("frappe", with_more_info=True)


def _request_context() -> dict[str, Any]:
	ctx: dict[str, Any] = {}
	try:
		ctx["site"] = getattr(frappe.local, "site", None)
		session = getattr(frappe.local, "session", None)
		ctx["user"] = getattr(session, "user", None) if session else None
		form_dict = getattr(frappe.local, "form_dict", None) or {}
		if hasattr(form_dict, "get"):
			ctx["cmd"] = form_dict.get("cmd")
		request = getattr(frappe.local, "request", None)
		if request is not None:
			ctx["path"] = getattr(request, "path", None)
			ctx["method"] = getattr(request, "method", None)
	except Exception:
		pass
	try:
		from frappe.monitor import get_trace_id

		ctx["trace_id"] = get_trace_id()
	except Exception:
		pass
	return ctx


def _format_log_error_title_and_traceback(
	title: str | None, message: str | None
) -> tuple[str, str]:
	"""Mirror frappe.utils.error.log_error title/traceback resolution."""
	traceback_text = None
	if message:
		if title and "\n" in title:
			traceback_text, title = title, message
		else:
			traceback_text = message

	title = title or "Error"
	traceback_text = frappe.as_unicode(traceback_text or frappe.get_traceback(with_context=True))
	return title, traceback_text


def _emit_full_error_log(
	*,
	title: str,
	traceback_text: str,
	exception: BaseException | None = None,
	source: str = "log_error",
) -> None:
	ctx = _request_context()
	exc_type = type(exception).__name__ if exception is not None else None
	header_parts = [f"Frappe {source}: {title}"]
	if exc_type and exc_type not in title:
		header_parts[0] = f"Frappe {source} [{exc_type}]: {title}"
	if ctx.get("site"):
		header_parts.append(f"site={ctx['site']}")
	if ctx.get("user"):
		header_parts.append(f"user={ctx['user']}")
	if ctx.get("cmd"):
		header_parts.append(f"cmd={ctx['cmd']}")
	elif ctx.get("path"):
		header_parts.append(f"path={ctx['path']}")
	if ctx.get("trace_id"):
		header_parts.append(f"trace_id={ctx['trace_id']}")

	message = f"{' | '.join(header_parts)}\n{traceback_text}"
	_error_logger().error(message)


def _patched_log_error(
	title=None,
	message=None,
	reference_doctype=None,
	reference_name=None,
	*,
	defer_insert=False,
):
	log_title, traceback_text = _format_log_error_title_and_traceback(title, message)
	result = _original_log_error(
		title=title,
		message=message,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		defer_insert=defer_insert,
	)
	_emit_full_error_log(title=log_title, traceback_text=traceback_text, source="log_error")
	return result


def _patched_log_error_snapshot(exception: Exception) -> None:
	if isinstance(exception, _EXCLUDE_EXCEPTIONS) or _is_ldap_exception(exception):
		return

	logger = _error_logger()
	try:
		# Persist to Error Log (same as Frappe) without the generic one-line logger call.
		_original_log_error(title=str(exception), defer_insert=True)
		traceback_text = frappe.get_traceback()
		_emit_full_error_log(
			title=str(exception),
			traceback_text=traceback_text,
			exception=exception,
			source="log_error_snapshot",
		)
	except Exception as e:
		logger.error("Could not take error snapshot: %s", e, exc_info=True)


def install_error_logging_for_newrelic() -> None:
	"""Patch Frappe error helpers once per process (idempotent)."""
	global _installed, _original_log_error
	global _EXCLUDE_EXCEPTIONS, _is_ldap_exception

	if _installed:
		return

	from frappe.utils import error as error_module

	_original_log_error = error_module.log_error
	_EXCLUDE_EXCEPTIONS = error_module.EXCLUDE_EXCEPTIONS
	_is_ldap_exception = error_module._is_ldap_exception

	error_module.log_error = _patched_log_error
	error_module.log_error_snapshot = _patched_log_error_snapshot

	# frappe.app imports log_error_snapshot at module load — patch that binding too.
	import frappe.app

	frappe.app.log_error_snapshot = _patched_log_error_snapshot

	# Public API used across apps.
	frappe.log_error = _patched_log_error

	_installed = True
