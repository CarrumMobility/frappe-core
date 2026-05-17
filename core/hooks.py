app_name = "core"
app_title = "Core"
app_publisher = "core"
app_description = "core"
app_email = "carrum_frappe_core@carrum.co.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "core",
# 		"logo": "/assets/core/logo.png",
# 		"title": "Core",
# 		"route": "/core",
# 		"has_permission": "core.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/core/css/core.css"
# app_include_js = "/assets/core/js/core.js"

# include js, css files in header of web template
# web_include_css = "/assets/core/css/core.css"
# web_include_js = "/assets/core/js/core.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "core/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "core/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Website route for SSO (cookie-based login). Served at /sso.
website_route_rules = [
	{"from_route": "/sso", "to_route": "sso"},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "core.utils.jinja_methods",
# 	"filters": "core.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "core.install.before_install"
# after_install = "core.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "core.uninstall.before_uninstall"
# after_uninstall = "core.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "core.utils.before_app_install"
# after_app_install = "core.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "core.utils.before_app_uninstall"
# after_app_uninstall = "core.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "core.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Call Session": {
		"on_update": "core.services.call_service.update_lead_last_call_date_time",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": ["core.services.call_service.reconcile_active_calls"],
	"hourly": [],
	"daily": [],
	"weekly": [],
	"daily_long": [],
	"hourly_long": [],
	"monthly_long": [],
	"cron": {
		# every day at IST time 12:05 AM, GMT time 06:35 PM (previous day)
    	# "35 18 * * *": ["core.services.agent_performance.agent_performance_service.cron_task_update_agent_performance"],

    	# every 5 minutes
    	"*/5 * * * *": [
        	"core.services.agent_performance.cron_task_update_today_telecaller_agents_performance_5_minute"
    	],
	},
}



# Testing
# -------

# before_tests = "core.install.before_tests"

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"User": "core.override.user.CustomUser",
	"File": "core.override.file.File",
	"Event": "core.override.event.CustomEvent",
}

write_file=["core.s3_file_hooks.write_file"]
delete_file_data_content=["core.s3_file_hooks.delete_file_data_content"]
# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "core.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "frappe.core.doctype.user.user.update_password": "core.services.util_service.blockPasswordChange",
    "frappe.core.doctype.user.user.reset_password": "core.services.util_service.blockPasswordChange"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "core.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["core.utils.before_request"]
# after_request = ["core.utils.after_request"]

# Job Events
# ----------
# before_job = ["core.utils.before_job"]
# after_job = ["core.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"core.auth.validate"
# ]

# Patch LoginManager so master password and other auth overrides apply
import frappe.auth
from core.override.auth import CustomLoginManager

frappe.auth.LoginManager = CustomLoginManager

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

before_request = [
	"core.services.site_home_redirect.maybe_redirect_site_root_to_external_url",
	"core.services.site_home_redirect.maybe_redirect_site_login_to_external_url",
	"core.services.util_service.blockDeskAccess",
]

after_request = [
	"core.observability.newrelic.enrich_newrelic_transaction",
]

after_migrate=["core.services.role_perm_service.enqueue_role_n_role_permission_creation_on_migration",]