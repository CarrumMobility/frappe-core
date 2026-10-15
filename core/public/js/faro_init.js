// Grafana Faro: browser monitoring for the Desk (page loads, Web Vitals,
// JS errors, AJAX timings, and a traceparent header on same-origin requests
// so browser and backend spans join into one trace).
//
// Runs only when the site's boot info carries `faro` (set by
// core.observability.faro.boot_session from site config). Loaded after the
// page is ready and fully async, so a CDN problem never affects the Desk.
// Session replay and console capture are off.

(function () {
	"use strict";

	var FARO_VERSION = "2.12.1";
	var CDN = "https://cdn.jsdelivr.net/npm/@grafana/";
	var BUNDLES = [
		{
			src: CDN + "faro-web-sdk@" + FARO_VERSION + "/dist/bundle/faro-web-sdk.iife.js",
			integrity: "sha384-l6Jzfv+lACs+s0S3b/ZzFKwCcMSqlSIAZHSVmK7zGeHg62sjKQgKJFnTYmkqLNBr",
		},
		{
			src:
				CDN + "faro-web-tracing@" + FARO_VERSION + "/dist/bundle/faro-web-tracing.iife.js",
			integrity: "sha384-GYXsSpSw1wyk0NGU1Sr3ueuCEPoOJRkS9l2BMVi8U57POeJm+PgV9e8pFRufOoBs",
		},
	];

	function config() {
		var boot = window.frappe && window.frappe.boot;
		return boot && boot.faro && boot.faro.url ? boot.faro : null;
	}

	function loadScript(bundle) {
		return new Promise(function (resolve, reject) {
			var el = document.createElement("script");
			el.src = bundle.src;
			el.integrity = bundle.integrity;
			el.crossOrigin = "anonymous";
			el.async = true;
			el.onload = resolve;
			el.onerror = reject;
			document.head.appendChild(el);
		});
	}

	function start(cfg) {
		var sdk = window.GrafanaFaroWebSdk;
		var tracing = window.GrafanaFaroWebTracing;
		if (!sdk || !tracing) return;

		sdk.initializeFaro({
			url: cfg.url,
			app: { name: cfg.app, environment: cfg.environment },
			instrumentations: sdk
				.getWebInstrumentations({ captureConsole: false })
				.concat([new tracing.TracingInstrumentation()]),
			// Realtime updates and the collector itself are noise.
			ignoreUrls: [
				/\/socket\.io\//,
				new RegExp("^" + cfg.url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
			],
			sessionTracking: { enabled: true },
		});
	}

	function init() {
		var cfg = config();
		if (!cfg || window.__carrumFaroLoading) return;
		window.__carrumFaroLoading = true;

		loadScript(BUNDLES[0])
			.then(function () {
				return loadScript(BUNDLES[1]);
			})
			.then(function () {
				start(cfg);
			})
			.catch(function () {
				// Blocked CDN or integrity mismatch: monitoring is skipped, the Desk is unaffected.
			});
	}

	if (document.readyState === "complete") {
		init();
	} else {
		window.addEventListener("load", init);
	}
})();
