import unittest
from unittest.mock import MagicMock, patch

import requests

from core.integrations.pazy import client as pazy_client
from core.integrations.pazy.client import PazyApiError, PazyClient


def _response(status_code, body):
	resp = MagicMock()
	resp.status_code = status_code
	resp.reason = "reason"
	resp.json.return_value = body
	resp.text = str(body)
	return resp


@patch.object(pazy_client.api_hit_service, "log_api_request")
class TestPazyClient(unittest.TestCase):
	def _create(self, api_key="test-key", **kwargs):
		return PazyClient(api_key).create_invoice(
			b"%PDF-1.4", "Invoice_Summary_bill-0001.pdf", "Maintenance portal | Bill x", **kwargs
		)

	@patch.object(pazy_client.requests, "post")
	def test_200_ok_returns_data(self, post, log):
		post.return_value = _response(200, {"ok": True, "data": {"id": "inv_1", "status": "QUEUED"}})
		self.assertEqual(self._create(user="a@b.c")["id"], "inv_1")
		self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Api-Key test-key"})
		self.assertEqual(post.call_args.args[0], "https://api.pazy.io/v1.0/invoice")
		self.assertEqual(log.call_args.args[0], "Pazy:create_invoice")
		self.assertEqual(log.call_args.args[2]["file_size"], 8)
		self.assertEqual(log.call_args.kwargs["created_by"], "a@b.c")
		self.assertNotIn("test-key", str(log.call_args))
		self.assertNotIn("headers", log.call_args.kwargs)

	@patch.object(pazy_client.requests, "post")
	def test_error_statuses_raise(self, post, _log):
		for status, body, code in (
			(
				400,
				{"ok": False, "error": {"code": "INVALID_FILE_TYPE", "message": "bad"}},
				"INVALID_FILE_TYPE",
			),
			(401, {"ok": False, "error": {"code": "INVALID_API_KEY"}}, "INVALID_API_KEY"),
			(413, "Payload Too Large", "PAYLOAD_TOO_LARGE"),
			(500, {"ok": False, "error": {"code": "INVOICE_CREATION_FAILED"}}, "INVOICE_CREATION_FAILED"),
			(200, {"ok": False}, "UNEXPECTED_RESPONSE"),
		):
			post.return_value = _response(status, body)
			with self.subTest(status=status), self.assertRaises(PazyApiError) as cm:
				self._create()
			self.assertEqual(cm.exception.status_code, status)
			self.assertEqual(cm.exception.code, code)

	@patch.object(pazy_client.requests, "post", side_effect=requests.Timeout("slow"))
	def test_timeout_raises_and_is_logged(self, _post, log):
		with self.assertRaises(PazyApiError) as cm:
			self._create()
		self.assertEqual(cm.exception.code, "TIMEOUT")
		self.assertIn("timed out", log.call_args.kwargs["error_message"])

	@patch.object(pazy_client.requests, "post", side_effect=requests.ConnectionError("down"))
	def test_connection_error_is_request_failed(self, _post, _log):
		with self.assertRaises(PazyApiError) as cm:
			self._create()
		self.assertEqual(cm.exception.code, "REQUEST_FAILED")

	@patch.object(pazy_client, "get_pazy_api_key", return_value="")
	def test_missing_api_key_raises(self, _key, _log):
		with self.assertRaises(PazyApiError):
			PazyClient().create_invoice(b"%PDF", "x.pdf", "r")
