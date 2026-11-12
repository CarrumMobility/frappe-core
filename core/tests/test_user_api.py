from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now
from frappe.utils.password import check_password

from core.api.user import generate_user_password

TEST_USER = "generated-password@example.com"
PLAIN_USER = "no-system-manager@example.com"


def _ensure_user(email: str) -> None:
	if frappe.db.exists("User", email):
		return
	# A bare row keeps the fixture free of welcome email, role and hook side effects.
	timestamp = now()
	user = frappe.qb.DocType("User")
	(
		frappe.qb.into(user)
		.columns("name", "email", "first_name", "enabled", "user_type", "creation", "modified", "owner", "modified_by")
		.insert(email, email, "Test", 1, "System User", timestamp, timestamp, "Administrator", "Administrator")
	).run()


class TestGenerateUserPassword(FrappeTestCase):
	def setUp(self):
		_ensure_user(TEST_USER)
		_ensure_user(PLAIN_USER)
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_returns_password_that_logs_the_user_in(self):
		result = generate_user_password(TEST_USER)

		self.assertEqual(result["user"], TEST_USER)
		self.assertEqual(check_password(TEST_USER, result["password"]), TEST_USER)

	def test_each_call_rotates_the_password(self):
		first = generate_user_password(TEST_USER)["password"]
		second = generate_user_password(TEST_USER)["password"]

		self.assertNotEqual(first, second)
		self.assertEqual(check_password(TEST_USER, second), TEST_USER)
		with self.assertRaises(frappe.AuthenticationError):
			check_password(TEST_USER, first)

	def test_matches_user_case_insensitively(self):
		result = generate_user_password(TEST_USER.upper())

		self.assertEqual(result["user"], TEST_USER)

	def test_unknown_user_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			generate_user_password("nobody@example.com")

	def test_administrator_is_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			generate_user_password("Administrator")

	def test_requires_system_manager(self):
		frappe.set_user(PLAIN_USER)

		# frappe.only_for is a no-op while flags.in_test is set.
		with patch.dict(frappe.flags, {"in_test": False}), self.assertRaises(frappe.PermissionError):
			generate_user_password(TEST_USER)
