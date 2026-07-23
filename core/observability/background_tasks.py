"""New Relic Non-Web transaction tracking for Frappe schedulers and queue workers."""

from __future__ import annotations

import frappe

SCHEDULED_JOB_METHOD = "frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job"
SCHEDULER_TASK_GROUP = "Scheduler"
QUEUE_TASK_GROUP = "Task"


def is_scheduled_job(method: str) -> bool:
	return SCHEDULED_JOB_METHOD in method


def scheduler_task_name(job_type: str) -> str:
	"""Build a readable New Relic background task name for a scheduled job."""
	if not job_type:
		return "Scheduler/unknown"

	func_name = job_type.rsplit(".", 1)[-1]
	readable = func_name.replace("_", " ").strip().title()
	return f"Scheduler {readable}"


def _get_agent():
	try:
		import newrelic.agent
	except ImportError:
		return None

	try:
		newrelic.agent.initialize()
	except Exception:
		pass

	return newrelic.agent


def _start_background_task(name: str, group: str) -> object | None:
	agent = _get_agent()
	if not agent:
		return None

	application = agent.application()
	if not application:
		return None

	task = agent.BackgroundTask(application, name=name, group=group)
	task.__enter__()
	frappe.local.newrelic_background_task = task
	return task


def _stop_background_task() -> None:
	task = getattr(frappe.local, "newrelic_background_task", None)
	if not task:
		return

	try:
		task.__exit__(None, None, None)
	finally:
		if hasattr(frappe.local, "newrelic_background_task"):
			del frappe.local.newrelic_background_task


def before_job(method, kwargs, transaction_type=None):
	agent = _get_agent()
	if not agent:
		return

	if is_scheduled_job(method):
		job_type = kwargs.get("job_type") or method
		task_name = scheduler_task_name(job_type)
		_start_background_task(task_name, SCHEDULER_TASK_GROUP)
		agent.add_custom_attribute("scheduled_job_name", job_type)
		agent.add_custom_attribute("frappe.site", frappe.local.site)
		return

	job = getattr(frappe.local, "job", None)
	queue = job.job_name if job else "default"
	_start_background_task(method, QUEUE_TASK_GROUP)
	agent.add_custom_attribute("job_name", method)
	agent.add_custom_attribute("queue", queue)
	agent.add_custom_attribute("frappe.site", frappe.local.site)


def after_job(method, kwargs, result=None):
	_stop_background_task()
