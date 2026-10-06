"""
Generic HTML -> PDF service.

Renders HTML (or a Jinja template) to PDF bytes with Frappe's wkhtmltopdf
wrapper and optionally stores the result as a File (which routes through S3
automatically when S3 storage is enabled, see core.s3_file_hooks.write_file).

Requires the wkhtmltopdf binary, 0.12.6 with patched Qt, on the server
(docs/technical/wkhtmltopdf_setup.md). QtWebKit does not support CSS flexbox
or grid: build templates with tables or absolute positioning.

Domain code (what goes into a document) stays with the caller; this module
only knows about HTML, PDF bytes and Files.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_url
from frappe.utils.pdf import get_pdf

# A4 portrait, no page margins: templates own their own spacing.
DEFAULT_PDF_OPTIONS = {
	"page-size": "A4",
	"orientation": "Portrait",
	"margin-top": "0mm",
	"margin-bottom": "0mm",
	"margin-left": "0mm",
	"margin-right": "0mm",
	"disable-smart-shrinking": None,
	"print-media-type": None,
	"background": None,
	"encoding": "UTF-8",
}


def render_html(template_path: str, context: dict | None = None) -> str:
	"""Render a Jinja template (path relative to an app, e.g. "core/templates/x.html")."""
	return frappe.render_template(template_path, context or {})


def html_to_pdf(html: str, pdf_options: dict | None = None) -> bytes:
	"""Render HTML to PDF bytes. `pdf_options` replaces DEFAULT_PDF_OPTIONS when given."""
	return get_pdf(html, options=dict(pdf_options or DEFAULT_PDF_OPTIONS))


def save_pdf(
	pdf_bytes: bytes,
	file_name: str,
	is_private: bool = True,
	attached_to_doctype: str | None = None,
	attached_to_name: str | None = None,
	attached_to_field: str | None = None,
):
	"""Store PDF bytes as a File and return the File document."""
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": pdf_bytes,
			"is_private": 1 if is_private else 0,
			"attached_to_doctype": attached_to_doctype,
			"attached_to_name": attached_to_name,
			"attached_to_field": attached_to_field,
		}
	).insert(ignore_permissions=True)


def read_file_bytes(file_doc) -> bytes:
	"""Bytes of a stored File, whether it lives on S3 or on the local filesystem."""
	from core.s3_file_storage import file_uses_s3, s3_get_bytes

	if file_uses_s3(file_doc):
		return s3_get_bytes(file_doc)
	content = file_doc.get_content()
	return content.encode("utf-8") if isinstance(content, str) else content


def absolute_file_url(file_url: str) -> str:
	"""S3 file URLs are already absolute; local /files and /private URLs are not."""
	if file_url.startswith(("http://", "https://")):
		return file_url
	return get_url(file_url)


def html_to_pdf_file(
	html: str,
	file_name: str = "document.pdf",
	is_private: bool = True,
	pdf_options: dict | None = None,
	attached_to_doctype: str | None = None,
	attached_to_name: str | None = None,
	attached_to_field: str | None = None,
):
	"""Render HTML to PDF and store it. Returns (File document, pdf bytes)."""
	pdf_bytes = html_to_pdf(html, pdf_options)
	file_doc = save_pdf(
		pdf_bytes,
		file_name,
		is_private=is_private,
		attached_to_doctype=attached_to_doctype,
		attached_to_name=attached_to_name,
		attached_to_field=attached_to_field,
	)
	return file_doc, pdf_bytes


def html_to_pdf_url(
	html: str,
	file_name: str = "document.pdf",
	is_private: bool = False,
	pdf_options: dict | None = None,
	attached_to_doctype: str | None = None,
	attached_to_name: str | None = None,
) -> str:
	"""Render HTML to PDF, store it as a File and return an absolute URL to it."""
	file_doc, _ = html_to_pdf_file(
		html,
		file_name=file_name,
		is_private=is_private,
		pdf_options=pdf_options,
		attached_to_doctype=attached_to_doctype,
		attached_to_name=attached_to_name,
	)
	return absolute_file_url(file_doc.file_url)
