from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from core.services.agent_performance import AgentPerformanceService


class TestAgentPerformanceCron(FrappeTestCase):
	def test_cron_commits_after_each_telecaller(self):
		"""Each agent's row lock is released right after its own update.

		Saving an Agent Performance doc takes an InnoDB row lock that is held until
		the transaction commits. The heartbeat endpoint writes the same row, so a
		single commit at the end of the loop blocks heartbeats for the whole run.
		"""
		service = AgentPerformanceService()
		recorder = MagicMock()

		with (
			patch.object(
				service,
				"_ensure_today_telecaller_agents_performance",
				return_value=["tc1@example.com", "tc2@example.com", "tc3@example.com"],
			),
			patch.object(service, "update_today_agent_performance_data_for_telecaller") as update_mock,
			patch.object(frappe.db, "commit") as commit_mock,
		):
			recorder.attach_mock(update_mock, "update")
			recorder.attach_mock(commit_mock, "commit")

			service.cron_task_update_today_telecaller_agents_performance_5_minute()

		self.assertEqual(
			recorder.mock_calls,
			[
				call.update("tc1@example.com"),
				call.commit(),
				call.update("tc2@example.com"),
				call.commit(),
				call.update("tc3@example.com"),
				call.commit(),
			],
		)
