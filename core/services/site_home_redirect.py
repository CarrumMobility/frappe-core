"""Optional redirect for bare site root (``/``) via ``site_config.json``."""

import frappe
from frappe.utils import cint


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

	from werkzeug.routing.exceptions import RequestRedirect

	exc = RequestRedirect(location)
	code = cint(frappe.conf.get("site_home_redirect_http_status")) or 302
	if code not in (301, 302, 303, 307, 308):
		code = 302
	exc.code = code
	raise exc
