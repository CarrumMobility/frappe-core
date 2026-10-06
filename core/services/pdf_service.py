from __future__ import annotations

import frappe
from frappe.utils import get_url
from frappe.utils.pdf import get_pdf

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


def html_to_pdf_url(
	html: str,
	file_name: str = "document.pdf",
	is_private: bool = False,
	pdf_options: dict | None = None,
	attached_to_doctype: str | None = None,
	attached_to_name: str | None = None,
) -> str:
	"""
	Render HTML to a PDF (via Frappe's wkhtmltopdf wrapper) and store it as a File
	(routes through S3 automatically when S3 storage is enabled, see
	core.s3_file_hooks.write_file).

	Requires the wkhtmltopdf binary (patched Qt build) on the server.

	Returns an absolute URL to the stored PDF.
	"""
	pdf_bytes = get_pdf(html, options=dict(pdf_options or DEFAULT_PDF_OPTIONS))

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": pdf_bytes,
			"is_private": 1 if is_private else 0,
			"attached_to_doctype": attached_to_doctype,
			"attached_to_name": attached_to_name,
		}
	).insert(ignore_permissions=True)

	file_url = file_doc.file_url
	if file_url.startswith(("http://", "https://")):
		return file_url
	return get_url(file_url)
