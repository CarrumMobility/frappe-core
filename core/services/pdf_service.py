"""
Generic HTML -> PDF service.

Renders HTML (or a Jinja template) to PDF bytes with Frappe's wkhtmltopdf
wrapper and optionally stores the result as a File.

Uniqueness guarantee: every save_pdf / html_to_pdf_file / html_to_pdf_url call
creates a new File whose stored object and file_url are unique, even when the
HTML and PDF bytes are identical to an earlier call. The caller's file_name is
kept as the display name; the stored name gets a random suffix. With S3 enabled
the bytes are uploaded here (bypassing Frappe's content-hash dedupe); without
S3 (local dev) a local File is created with duplicate reuse disabled.

Requires the wkhtmltopdf binary, 0.12.6 with patched Qt, on the server
(docs/technical/wkhtmltopdf_setup.md). QtWebKit does not support CSS flexbox
or grid: build templates with tables or absolute positioning.

Domain code (what goes into a document) stays with the caller; this module
only knows about HTML, PDF bytes and Files.
"""

from __future__ import annotations

import functools
import os
import re

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
	"""Store PDF bytes as a File with a unique stored name/URL and return the File document."""
	from core.s3_file_storage import build_object_key, public_file_url, s3_enabled, s3_put_bytes

	stem, ext = os.path.splitext(re.sub(r"[/\\%?#]", "_", file_name or "document.pdf"))
	unique_name = f"{stem or 'document'}_{frappe.generate_hash(length=16)}{ext}"
	values = {
		"doctype": "File",
		"is_private": 1 if is_private else 0,
		"attached_to_doctype": attached_to_doctype,
		"attached_to_name": attached_to_name,
		"attached_to_field": attached_to_field,
	}

	if s3_enabled():
		site = getattr(frappe.local, "site", "") or "site"
		key = build_object_key(site, is_private, unique_name)
		s3_put_bytes(key, pdf_bytes, unique_name)
		values.update({"file_name": file_name, "file_url": public_file_url(key), "file_size": len(pdf_bytes)})
		return frappe.get_doc(values).insert(ignore_permissions=True)

	values.update({"file_name": unique_name, "content": pdf_bytes})
	file_doc = frappe.get_doc(values)
	file_doc.flags.ignore_duplicate_entry_error = True
	# File.save_file reuses an existing File with the same content hash; skip that lookup.
	file_doc.save_file = functools.partial(
		type(file_doc).save_file, file_doc, ignore_existing_file_check=True
	)
	return file_doc.insert(ignore_permissions=True)


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
