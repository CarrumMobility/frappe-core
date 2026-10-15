"""Grafana Faro (browser monitoring) settings for the Desk.

boot_session copies the Faro settings from site config into ``frappe.boot``,
where /assets/core/js/faro_init.js picks them up. A site without
``faro_collect_url`` gets nothing, so the script stays inert there.

Config keys (written to common_site_config.json by erpnext-config):
    faro_collect_url   e.g. https://faro.carrum.co.in/collect
    faro_app_name      default "erpnext"
    faro_environment   e.g. "dev"
"""

from __future__ import annotations

import frappe


def boot_session(bootinfo) -> None:
	conf = frappe.conf or {}
	url = conf.get("faro_collect_url")
	if not url:
		return

	bootinfo.faro = {
		"url": url,
		"app": conf.get("faro_app_name") or "erpnext",
		"environment": conf.get("faro_environment") or "unknown",
	}
