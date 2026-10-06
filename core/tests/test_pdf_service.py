from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from core.services import pdf_service

PREFIX = "https://bucket.example.com"


def _blank_pdf() -> bytes:
	writer = PdfWriter()
	writer.add_blank_page(width=100, height=100)
	buf = BytesIO()
	writer.write(buf)
	return buf.getvalue()


PDF = _blank_pdf()


class TestPdfServiceUniqueUrls(FrappeTestCase):
	def setUp(self):
		self._names = []

	def tearDown(self):
		frappe.db.rollback()
		for name in self._names:
			if frappe.db.exists("File", name):
				frappe.delete_doc("File", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _save(self, **kw):
		doc = pdf_service.save_pdf(PDF, "Invoice_Summary_X.pdf", **kw)
		self._names.append(doc.name)
		return doc

	def test_s3_enabled_urls_unique(self):
		site = frappe.local.site
		with (
			patch("core.s3_file_storage.s3_enabled", return_value=True),
			patch("core.s3_file_storage.s3_bucket_prefix", return_value=PREFIX),
			patch("core.s3_file_storage.s3_put_bytes") as put,
		):
			a = self._save(is_private=True)
			b = self._save(is_private=True)

		self.assertNotEqual(a.file_url, b.file_url)
		self.assertTrue(a.file_url.startswith(PREFIX))
		self.assertTrue(b.file_url.startswith(PREFIX))
		self.assertEqual(a.file_name, "Invoice_Summary_X.pdf")
		self.assertEqual(put.call_count, 2)
		keys = [c.args[0] for c in put.call_args_list]
		self.assertNotEqual(keys[0], keys[1])
		for key in keys:
			self.assertTrue(key.startswith(f"{site}/private/files/"))
		self.assertEqual(a.file_url, f"{PREFIX}/{keys[0]}")

	def test_s3_disabled_urls_unique(self):
		with patch("core.s3_file_storage.s3_enabled", return_value=False):
			a = self._save(is_private=False)
			b = self._save(is_private=False)
		self.assertNotEqual(a.file_url, b.file_url)
		self.assertNotEqual(a.name, b.name)

	def test_html_to_pdf_url_unique(self):
		with (
			patch.object(pdf_service, "html_to_pdf", return_value=PDF),
			patch("core.s3_file_storage.s3_enabled", return_value=False),
		):
			u1 = pdf_service.html_to_pdf_url("<p>same</p>", file_name="x.pdf")
			u2 = pdf_service.html_to_pdf_url("<p>same</p>", file_name="x.pdf")
		for f in frappe.get_all(
			"File", filters={"file_url": ("in", [u1.split("/", 3)[-1], u2.split("/", 3)[-1]])}
		):
			self._names.append(f.name)
		self.assertNotEqual(u1, u2)
		self.assertTrue(u1.startswith(("http://", "https://")))
