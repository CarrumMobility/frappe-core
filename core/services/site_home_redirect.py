"""Optional external redirects for ``/`` and ``/login`` via ``site_config.json``."""

import frappe
from frappe.utils import cint


def _raise_request_redirect(location: str, status_conf_key: str) -> None:
	from werkzeug.routing.exceptions import RequestRedirect

	exc = RequestRedirect(location)
	code = cint(frappe.conf.get(status_conf_key)) or 302
	if code not in (301, 302, 303, 307, 308):
		code = 302
	exc.code = code
	raise exc


def maybe_redirect_site_root_to_external_url() -> None:
	"""If ``site_home_redirect_url`` is set, send GET/HEAD ``/`` to that URL.

	Configure in ``site_config.json``::

	    "site_home_redirect_url": "https://www.example.com/",
	    "site_home_redirect_http_status": 302

	``site_home_redirect_http_status`` is optional; allowed values are 301, 302,
	303, 307, 308 (default 302).
	"""
	target = (frappe.conf.get("site_home_redirect_url") or "").strip()
	if not target:
		return

	if frappe.request.method not in ("GET", "HEAD"):
		return

	if (frappe.request.path or "") != "/":
		return

	if not (target.startswith("https://") or target.startswith("http://")):
		frappe.log_error(
			title="Invalid site_home_redirect_url",
			message="site_home_redirect_url must start with http:// or https://",
		)
		return

	qs = frappe.request.query_string
	if qs:
		sep = "&" if "?" in target else "?"
		location = target + sep + frappe.safe_decode(qs)
	else:
		location = target

	_raise_request_redirect(location, "site_home_redirect_http_status")


def maybe_redirect_site_login_to_external_url() -> None:
	"""If ``site_login_redirect_url`` is set, send GET/HEAD ``/login`` to that URL.

	Configure in ``site_config.json``::

	    "site_login_redirect_url": "https://auth.example.com/login",
	    "site_login_redirect_http_status": 302

	``site_login_redirect_http_status`` is optional; allowed values are 301, 302,
	303, 307, 308 (default 302).

	Trailing slashes on the request path are ignored (``/login`` and ``/login/``).
	"""
	target = (frappe.conf.get("site_login_redirect_url") or "").strip()
	if not target:
		return

	if frappe.request.method not in ("GET", "HEAD"):
		return

	norm = (frappe.request.path or "").rstrip("/") or "/"
	if norm != "/login":
		return

	if not (target.startswith("https://") or target.startswith("http://")):
		frappe.log_error(
			title="Invalid site_login_redirect_url",
			message="site_login_redirect_url must start with http:// or https://",
		)
		return

	qs = frappe.request.query_string
	if qs:
		sep = "&" if "?" in target else "?"
		location = target + sep + frappe.safe_decode(qs)
	else:
		location = target

	_raise_request_redirect(location, "site_login_redirect_http_status")
