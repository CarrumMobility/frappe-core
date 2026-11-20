"""Frappe-version compatibility of the New Relic error-logging shim.

Frappe v15 exposes ``frappe.utils.error.EXCLUDE_EXCEPTIONS``. Frappe v16.53
removed that tuple (frappe/frappe#40610) and marks the excluded exception
classes with ``skip_error_log = True`` instead. The shim runs at import time
from ``core.hooks``, so a hard dependency on either shape breaks
``bench build`` for every site on the other version.

These tests need no site or database.
"""

import types
import unittest
from unittest.mock import patch

import frappe
import frappe.app
from frappe.utils import error as error_module

from core.observability import error_logging


class _Expected(Exception):
	skip_error_log = True


def _no_ldap(_exception):
	return False


class TestErrorLoggingFrappeCompat(unittest.TestCase):
	def test_exclusions_empty_when_frappe_has_no_tuple(self):
		fake_module = types.SimpleNamespace()  # Frappe v16.53+
		self.assertEqual(error_logging._exclude_exceptions_from(fake_module), ())

	def test_exclusions_read_from_v15_tuple(self):
		fake_module = types.SimpleNamespace(EXCLUDE_EXCEPTIONS=(frappe.AuthenticationError,))
		self.assertEqual(error_logging._exclude_exceptions_from(fake_module), (frappe.AuthenticationError,))

	def test_skip_error_log_flag_is_honoured_without_tuple(self):
		with (
			patch.object(error_logging, "_EXCLUDE_EXCEPTIONS", ()),
			patch.object(error_logging, "_is_ldap_exception", _no_ldap),
		):
			self.assertTrue(error_logging._should_skip_snapshot(_Expected("expected")))
			self.assertFalse(error_logging._should_skip_snapshot(ValueError("unexpected")))

	def test_v15_exclude_tuple_is_honoured(self):
		with (
			patch.object(error_logging, "_EXCLUDE_EXCEPTIONS", (frappe.AuthenticationError,)),
			patch.object(error_logging, "_is_ldap_exception", _no_ldap),
		):
			self.assertTrue(error_logging._should_skip_snapshot(frappe.AuthenticationError()))
			self.assertFalse(error_logging._should_skip_snapshot(ValueError("unexpected")))

	def test_ldap_exceptions_are_still_skipped(self):
		with (
			patch.object(error_logging, "_EXCLUDE_EXCEPTIONS", ()),
			patch.object(error_logging, "_is_ldap_exception", lambda e: True),
		):
			self.assertTrue(error_logging._should_skip_snapshot(ValueError("ldap")))

	def test_install_succeeds_when_frappe_has_no_exclude_tuple(self):
		"""Regression: Frappe v16.53 removed EXCLUDE_EXCEPTIONS and importing
		core.hooks raised AttributeError, killing `bench build`."""
		had_tuple = hasattr(error_module, "EXCLUDE_EXCEPTIONS")
		saved_tuple = getattr(error_module, "EXCLUDE_EXCEPTIONS", None)
		if had_tuple:
			delattr(error_module, "EXCLUDE_EXCEPTIONS")
		try:
			with (
				patch.object(error_module, "log_error"),
				patch.object(error_module, "log_error_snapshot"),
				patch.object(frappe.app, "log_error_snapshot"),
				patch.object(frappe, "log_error"),
				patch.object(error_logging, "_installed", False),
				patch.object(error_logging, "_original_log_error", None),
				patch.object(error_logging, "_EXCLUDE_EXCEPTIONS", None),
				patch.object(error_logging, "_is_ldap_exception", None),
			):
				error_logging.install_error_logging_for_newrelic()

				self.assertTrue(error_logging._installed)
				self.assertEqual(error_logging._EXCLUDE_EXCEPTIONS, ())
				self.assertIs(error_module.log_error_snapshot, error_logging._patched_log_error_snapshot)
				self.assertIs(frappe.app.log_error_snapshot, error_logging._patched_log_error_snapshot)
				self.assertIs(frappe.log_error, error_logging._patched_log_error)
				# The flag Frappe v16 relies on still short-circuits the snapshot.
				error_logging._patched_log_error_snapshot(_Expected("expected"))
				error_logging._original_log_error.assert_not_called()
		finally:
			if had_tuple:
				error_module.EXCLUDE_EXCEPTIONS = saved_tuple

	def test_install_succeeds_when_frappe_has_exclude_tuple(self):
		"""Frappe v15 shape: the tuple is still used for the isinstance check."""
		with (
			patch.object(error_module, "EXCLUDE_EXCEPTIONS", (frappe.AuthenticationError,), create=True),
			patch.object(error_module, "log_error"),
			patch.object(error_module, "log_error_snapshot"),
			patch.object(frappe.app, "log_error_snapshot"),
			patch.object(frappe, "log_error"),
			patch.object(error_logging, "_installed", False),
			patch.object(error_logging, "_original_log_error", None),
			patch.object(error_logging, "_EXCLUDE_EXCEPTIONS", None),
			patch.object(error_logging, "_is_ldap_exception", None),
		):
			error_logging.install_error_logging_for_newrelic()

			self.assertEqual(error_logging._EXCLUDE_EXCEPTIONS, (frappe.AuthenticationError,))
			error_logging._patched_log_error_snapshot(frappe.AuthenticationError())
			error_logging._original_log_error.assert_not_called()


if __name__ == "__main__":
	unittest.main()
