"""
Carrum "Tax Invoice Summary" PDF (format CARRUM-PAZY-STD v2.1).

Template: apps/core/core/templates/pdf/carrum_invoice_summary.html
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.utils import flt, fmt_money, format_datetime, formatdate
from num2words import num2words

from core.services.pdf_service import html_to_pdf_url

TEMPLATE_PATH = "core/templates/pdf/carrum_invoice_summary.html"
FORMAT_CODE = "CARRUM-PAZY-STD v2.1"

# Global Config (key=HUB_GSTIN_CONFIG_KEY) holds Carrum's own GSTIN/address per
# hub, as a JSON array matching the "hub_business_type" config's shape:
# [{"hubName": "bengaluru", "gstin": "...", "address": "..."}, ...]
# (hubName there is lowercase; Maintenance Bill.hub_name is capitalized, e.g.
# "Bengaluru" - the lookup below compares case-insensitively.)
# Same Global Config lookup pattern as crm.module_maintenance.tax_invoice_adherence._get_adherence_factors.
HUB_GSTIN_CONFIG_KEY = "hub_gstin_config"

COMPANY_NAME = "Carrum Mobility Solutions Pvt. Ltd."
# Fallback when a hub has no entry (or no entry exists at all) in Global Config.
DEFAULT_COMPANY_GSTIN = "06AAFCC8123M1Z9"
DEFAULT_COMPANY_ADDRESS = "Sector 44, Gurugram, Haryana 122003"


def _get_hub_company_details(hub_name: str | None) -> tuple[str, str]:
	"""(gstin, address) for `hub_name` from Global Config, falling back to defaults."""
	try:
		raw = frappe.db.get_value("Global Config", {"key": HUB_GSTIN_CONFIG_KEY}, "value")
		if raw and hub_name:
			config = json.loads(raw) if isinstance(raw, str) else raw
			entries = config if isinstance(config, list) else [config]
			for entry in entries:
				if str(entry.get("hubName", "")).strip().lower() == hub_name.strip().lower():
					gstin = entry.get("gstin")
					address = entry.get("address")
					if gstin or address:
						return gstin or DEFAULT_COMPANY_GSTIN, address or DEFAULT_COMPANY_ADDRESS
					break
	except Exception:
		pass
	return DEFAULT_COMPANY_GSTIN, DEFAULT_COMPANY_ADDRESS

PDF_OPTIONS = {
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


def fmt(value) -> str:
	"""12450 -> '12,450.00' (follows System Settings number format)."""
	return fmt_money(flt(value, 2), precision=2)


def rupees_in_words(amount) -> str:
	"""20773.90 -> 'Rupees Twenty Thousand Seven Hundred Seventy Three and Ninety Paise Only'."""
	amount = round(flt(amount), 2)
	rupees = int(amount)
	paise = int(round((amount - rupees) * 100))

	def words(n):
		s = num2words(n, lang="en_IN")
		s = re.sub(r"[-,]", " ", s)
		s = re.sub(r"\band\b", " ", s)
		return " ".join(w.capitalize() for w in s.split())

	text = f"Rupees {words(rupees)}"
	if paise:
		text += f" and {words(paise)} Paise"
	return text + " Only"


def render_invoice_summary_html(data: dict) -> str:
	"""Render the Jinja template. `data` shape is shown in SAMPLE_DATA below."""
	data = frappe._dict(data)
	data.setdefault("format_code", FORMAT_CODE)
	data.setdefault("amount_in_words", rupees_in_words(data.total_invoice_amount))
	return frappe.render_template(TEMPLATE_PATH, {"d": data, "fmt": fmt})


def get_invoice_summary_pdf_url(
	data: dict,
	file_name: str | None = None,
	is_private: bool = True,
	attached_to_doctype: str | None = None,
	attached_to_name: str | None = None,
) -> str:
	"""Render the invoice summary HTML, convert to PDF, store it (S3 when enabled) and return its URL."""
	html = render_invoice_summary_html(data)
	name = file_name or f"Invoice_Summary_{data.get('portal_bill_id', frappe.generate_hash(length=8))}.pdf"
	return html_to_pdf_url(
		html,
		file_name=name,
		is_private=is_private,
		pdf_options=PDF_OPTIONS,
		attached_to_doctype=attached_to_doctype,
		attached_to_name=attached_to_name,
	)


def build_context(doc) -> dict:
	"""
	Map a Maintenance Bill document to the template data.

	Parts/Labour taxable amounts, discounts and GST come from the bill's own
	aggregate fields (part_total/labour_total/*_cgst_amount/etc.) rather than
	the Maintenance Bill Part rows, since those aggregates are the figures the
	bill was actually approved against.
	"""
	line_items = []

	parts_gst = flt(doc.parts_cgst_amount) + flt(doc.parts_sgst_amount) + flt(doc.parts_igst_amount)
	if doc.part_total or doc.part_discount or parts_gst:
		taxable = flt(doc.part_total)
		discount = flt(doc.part_discount)
		line_items.append(
			frappe._dict(
				particulars="Parts / Spares",
				taxable=taxable,
				discount=discount,
				gst=parts_gst,
				tds=0,
				total=taxable - discount + parts_gst,
			)
		)

	labour_gst = flt(doc.labour_cgst_amount) + flt(doc.labour_sgst_amount) + flt(doc.labour_igst_amount)
	labour_tds = flt(doc.labour_tds_amount)
	if doc.labour_total or doc.labour_discount or labour_gst:
		taxable = flt(doc.labour_total)
		discount = flt(doc.labour_discount)
		line_items.append(
			frappe._dict(
				particulars="Labour / Service",
				taxable=taxable,
				discount=discount,
				gst=labour_gst,
				tds=labour_tds,
				total=taxable - discount + labour_gst,
			)
		)

	gst_heads = []
	if parts_gst:
		if doc.parts_cgst_amount:
			gst_heads.append({"head": f"CGST (Parts) {flt(doc.parts_cgst_rate)}%", "amount": flt(doc.parts_cgst_amount)})
		if doc.parts_sgst_amount:
			gst_heads.append({"head": f"SGST (Parts) {flt(doc.parts_sgst_rate)}%", "amount": flt(doc.parts_sgst_amount)})
		if doc.parts_igst_amount:
			gst_heads.append({"head": f"IGST (Parts) {flt(doc.parts_igst_rate)}%", "amount": flt(doc.parts_igst_amount)})
	if labour_gst:
		if doc.labour_cgst_amount:
			gst_heads.append({"head": f"CGST (Labour) {flt(doc.labour_cgst_rate)}%", "amount": flt(doc.labour_cgst_amount)})
		if doc.labour_sgst_amount:
			gst_heads.append({"head": f"SGST (Labour) {flt(doc.labour_sgst_rate)}%", "amount": flt(doc.labour_sgst_amount)})
		if doc.labour_igst_amount:
			gst_heads.append({"head": f"IGST (Labour) {flt(doc.labour_igst_rate)}%", "amount": flt(doc.labour_igst_amount)})

	tds_heads = []
	if labour_tds:
		tds_heads.append({"head": f"TDS on Labour {flt(doc.labour_tds_percent)}%", "amount": labour_tds})

	total_invoice = flt(doc.net_gross_value_amount) or sum(g.total for g in line_items)
	total_gst = flt(doc.net_gst_amount) or parts_gst + labour_gst
	total_tds = labour_tds
	net_payable = flt(doc.net_amount) or (total_invoice - total_tds)

	approver_user = doc.finance_approved_by 
	approver = frappe.db.get_value("User", approver_user, "full_name") or approver_user
	company_gstin, company_address = _get_hub_company_details(doc.hub_name)

	return {
		"portal_bill_id": doc.maintenance_ticket_id or doc.name,
		"workshop_display_name": doc.workshop_name or "",
		"workshop_gst_no": doc.workshop_gst_no or "",
		"company_name": COMPANY_NAME,
		"company_gstin": company_gstin,
		"company_address": company_address,
		"invoice_no": doc.bill_no,
		"invoice_date": formatdate(doc.bill_issue_date, "dd-MM-yyyy") if doc.bill_issue_date else "",
		"vehicle_no": doc.reg_number or "",
		"cost_center": doc.hub_name or "",
		"line_items": line_items,
		"total_invoice_amount": total_invoice,
		"total_tds": total_tds,
		"net_payable": net_payable,
		"gst_heads": gst_heads,
		"total_gst": total_gst,
		"tds_heads": tds_heads,
		"narration": doc.narration or "",
		"approved_by": approver,
		"approved_on": format_datetime(doc.finance_approved_date , "dd-MM-yyyy HH:mm") + " IST",
	}


@frappe.whitelist()
def generate_invoice_summary_pdf(name: str) -> str:
	"""
	GET /api/method/core.services.invoice_summary_pdf.generate_invoice_summary_pdf?name=<Maintenance Bill name>
	Generates the invoice summary PDF for a Maintenance Bill, stores it, and returns its URL.
	"""
	doc = frappe.get_doc("Maintenance Bill", name)
	doc.check_permission("write")
	return get_invoice_summary_pdf_url(
		build_context(doc),
		attached_to_doctype="Maintenance Bill",
		attached_to_name=name,
	)


SAMPLE_DATA = {
	"portal_bill_id": "CRM-BILL-2026-091143",
	"workshop_display_name": "Shree Balaji Auto Care Pvt. Ltd.",
	"workshop_gst_no": "06AABCS1429R1ZK",
	"company_name": "Carrum Mobility Solutions Pvt. Ltd.",
	"company_gstin": "06AAFCC8123M1Z9",
	"company_address": "Sector 44, Gurugram, Haryana 122003",
	"invoice_no": "SBA/25-26/04187",
	"invoice_date": "28-08-2026",
	"vehicle_no": "HR26EK4471",
	"cost_center": "GGN-FLEET-RENTAL",
	"line_items": [
		{"particulars": "Parts / Spares", "taxable": 12450, "discount": 1245, "gst": 2016.90, "tds": 0, "total": 13221.90},
		{"particulars": "Labour / Service", "taxable": 6800, "discount": 400, "gst": 1152.00, "tds": 128, "total": 7552.00},
	],
	"total_invoice_amount": 20773.90,
	"total_tds": 128.00,
	"net_payable": 20645.90,
	"gst_heads": [
		{"head": "CGST-Input(Haryana) 9%", "amount": 1584.45},
		{"head": "SGST-Input(Haryana) 9%", "amount": 1584.45},
	],
	"total_gst": 3168.90,
	"tds_heads": [{"head": "194C 2% TDS on Contractor", "amount": 128.00}],
	"narration": "Being Repair & Maintenance Expense booked for HR26EK4471 against SBA/25-26/04187",
	"approved_by": "Finance - Priya Nair",
	"approved_on": "24-09-2026 11:40 IST",
}


def test_sample_pdf_url() -> str:
	"""bench --site <site> execute core.services.invoice_summary_pdf.test_sample_pdf_url"""
	return get_invoice_summary_pdf_url(SAMPLE_DATA)
