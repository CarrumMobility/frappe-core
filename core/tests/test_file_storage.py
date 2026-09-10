from unittest.mock import Mock, patch

import frappe
from frappe.core.doctype.file.file import File as FrappeFile
from frappe.tests.utils import FrappeTestCase
from pydantic import ValidationError

from core.api.utils import EnvConfig
from core.file_storage import FileStorageType, get_file_storage_type
from core.override.file import File


def _env_config(**overrides):
	values = {
		"master_password": "test",
		"chatwoot_account_id": 1,
		"chatwoot_base_url": "https://chat.example.com",
		"carrum_base_url": "https://api.example.com",
		"carrum_token": "token",
		"db_name": "db",
		"db_password": "password",
		"db_type": "mariadb",
		"allow_tests": True,
		"developer_mode": True,
		"encryption_key": "key",
		"env": "TEST",
		"old_carrum_base_url": "https://old-api.example.com",
		"old_carrum_token": "old-token",
		"smartflo_admin_password": "password",
		"smartflo_admin_username": "user",
	}
	values.update(overrides)
	return values


class TestFileStorageSelection(FrappeTestCase):
	def test_absent_selector_defaults_to_default(self):
		self.assertEqual(get_file_storage_type(frappe._dict()), FileStorageType.DEFAULT)

	def test_supported_selectors_are_exact(self):
		for storage_type in FileStorageType:
			self.assertEqual(
				get_file_storage_type(frappe._dict(file_storage_type=storage_type.value)),
				storage_type,
			)

	def test_invalid_or_lowercase_selector_raises(self):
		for value in ("gcs", "LOCAL", 1):
			with self.assertRaises(frappe.ValidationError):
				get_file_storage_type(frappe._dict(file_storage_type=value))

	def test_legacy_flag_does_not_enable_s3(self):
		conf = frappe._dict(s3_file_storage_enabled=1)
		self.assertEqual(get_file_storage_type(conf), FileStorageType.DEFAULT)


class TestEnvironmentStorageValidation(FrappeTestCase):
	def test_default_and_gcs_do_not_require_s3_fields(self):
		self.assertEqual(EnvConfig(**_env_config()).file_storage_type, FileStorageType.DEFAULT)
		config = EnvConfig(
			**_env_config(file_storage_type="GCS", gcs_bucket="files"),
		)
		self.assertEqual(config.file_storage_type, FileStorageType.GCS)

	def test_s3_requires_bucket(self):
		with self.assertRaises(ValidationError):
			EnvConfig(**_env_config(file_storage_type="S3"))

	def test_gcs_requires_bucket(self):
		with self.assertRaises(ValidationError):
			EnvConfig(**_env_config(file_storage_type="GCS"))

	def test_s3_credentials_must_be_a_pair(self):
		with self.assertRaises(ValidationError):
			EnvConfig(
				**_env_config(
					file_storage_type="S3",
					s3_bucket="files",
					aws_access_key_id="access",
				)
			)


class TestFileStorageHooks(FrappeTestCase):
	def _file_doc(self, private=1):
		doc = Mock()
		doc.file_name = "invoice.pdf"
		doc.content_hash = "1234567890abcdef"
		doc._content = b"content"
		doc.is_private = private
		return doc

	def test_default_write_uses_filesystem_only(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		doc.save_file_on_filesystem.return_value = {"file_name": doc.file_name}
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.DEFAULT),
			patch.object(s3_file_hooks, "s3_put_bytes") as s3_put,
			patch.object(s3_file_hooks, "gcs_put_bytes") as gcs_put,
		):
			result = s3_file_hooks.write_file(doc)
		doc.save_file_on_filesystem.assert_called_once_with()
		s3_put.assert_not_called()
		gcs_put.assert_not_called()
		self.assertEqual(result, {"file_name": "invoice.pdf"})

	def test_s3_write_uses_only_s3(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.S3),
			patch.object(s3_file_hooks, "s3_put_bytes") as s3_put,
			patch.object(s3_file_hooks, "gcs_put_bytes") as gcs_put,
			patch.object(s3_file_hooks, "public_file_url", return_value="/private/files/invoice.pdf"),
		):
			s3_file_hooks.write_file(doc)
		s3_put.assert_called_once()
		gcs_put.assert_not_called()
		doc.save_file_on_filesystem.assert_not_called()

	def test_gcs_write_uses_only_gcs(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.GCS),
			patch.object(s3_file_hooks, "require_gcs_config"),
			patch.object(s3_file_hooks, "s3_put_bytes") as s3_put,
			patch.object(s3_file_hooks, "gcs_put_bytes") as gcs_put,
			patch.object(s3_file_hooks, "gcs_file_url", return_value="/private/files/invoice.pdf"),
		):
			s3_file_hooks.write_file(doc)
		gcs_put.assert_called_once()
		s3_put.assert_not_called()
		doc.save_file_on_filesystem.assert_not_called()

	def test_gcs_write_failure_does_not_fall_back_to_filesystem(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.GCS),
			patch.object(s3_file_hooks, "require_gcs_config"),
			patch.object(s3_file_hooks, "gcs_put_bytes", side_effect=RuntimeError("upload failed")),
		):
			with self.assertRaisesRegex(RuntimeError, "upload failed"):
				s3_file_hooks.write_file(doc)
		doc.save_file_on_filesystem.assert_not_called()

	def test_gcs_delete_uses_only_gcs(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.GCS),
			patch.object(s3_file_hooks, "file_uses_gcs", return_value=True),
			patch.object(s3_file_hooks, "gcs_delete") as gcs_delete,
			patch.object(s3_file_hooks, "s3_delete") as s3_delete,
		):
			s3_file_hooks.delete_file_data_content(doc)
		gcs_delete.assert_called_once_with(doc)
		s3_delete.assert_not_called()
		doc.delete_file_from_filesystem.assert_not_called()

	def test_s3_delete_uses_only_s3(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.S3),
			patch.object(s3_file_hooks, "s3_enabled", return_value=True),
			patch.object(s3_file_hooks, "file_uses_s3", return_value=True),
			patch.object(s3_file_hooks, "gcs_delete") as gcs_delete,
			patch.object(s3_file_hooks, "s3_delete") as s3_delete,
		):
			s3_file_hooks.delete_file_data_content(doc)
		s3_delete.assert_called_once_with(doc)
		gcs_delete.assert_not_called()
		doc.delete_file_from_filesystem.assert_not_called()

	def test_default_delete_uses_only_filesystem(self):
		from core import s3_file_hooks

		doc = self._file_doc()
		with (
			patch.object(s3_file_hooks, "get_file_storage_type", return_value=FileStorageType.DEFAULT),
			patch.object(s3_file_hooks, "gcs_delete") as gcs_delete,
			patch.object(s3_file_hooks, "s3_delete") as s3_delete,
		):
			s3_file_hooks.delete_file_data_content(doc)
		doc.delete_file_from_filesystem.assert_called_once_with(only_thumbnail=False)
		gcs_delete.assert_not_called()
		s3_delete.assert_not_called()


class TestS3StorageSelection(FrappeTestCase):
	def test_selected_s3_without_bucket_raises(self):
		from core import s3_file_storage

		conf = frappe._dict(file_storage_type="S3")
		with patch.object(s3_file_storage.frappe, "conf", conf):
			with self.assertRaises(frappe.ValidationError):
				s3_file_storage.s3_enabled()

	def test_existing_s3_key_and_url_layout_is_preserved(self):
		from core import s3_file_storage

		conf = frappe._dict(s3_bucket_prefix="https://files.example.com")
		with patch.object(s3_file_storage.frappe, "conf", conf):
			key = s3_file_storage.build_object_key("dev", True, "a.pdf")
			self.assertEqual(key, "dev/private/files/a.pdf")
			self.assertEqual(
				s3_file_storage.public_file_url(key),
				"https://files.example.com/dev/private/files/a.pdf",
			)


class TestGCSStorage(FrappeTestCase):
	def test_client_uses_application_default_credentials(self):
		from core import gcs_file_storage

		with (
			patch.object(gcs_file_storage, "require_gcs_config"),
			patch.object(gcs_file_storage.storage, "Client") as client,
		):
			gcs_file_storage.gcs_client()
		client.assert_called_once_with()

	def test_private_and_public_urls(self):
		from core import gcs_file_storage

		conf = frappe._dict(gcs_bucket="files")
		with patch.object(gcs_file_storage.frappe, "conf", conf):
			self.assertEqual(
				gcs_file_storage.file_url("dev/private/files/a.pdf", True),
				"/private/files/a.pdf",
			)
			self.assertEqual(
				gcs_file_storage.file_url("dev/files/a.pdf", False),
				"https://storage.googleapis.com/files/dev/files/a.pdf",
			)

	def test_public_prefix_and_object_key_round_trip(self):
		from core import gcs_file_storage

		conf = frappe._dict(
			file_storage_type="GCS",
			gcs_bucket="files",
			gcs_bucket_prefix="https://cdn.example.com",
		)
		doc = frappe._dict(file_url="https://cdn.example.com/dev/files/a.pdf")
		with patch.object(gcs_file_storage.frappe, "conf", conf):
			self.assertEqual(
				gcs_file_storage.file_url("dev/files/a.pdf", False),
				"https://cdn.example.com/dev/files/a.pdf",
			)
			self.assertEqual(gcs_file_storage.gcs_object_key(doc), "dev/files/a.pdf")

	def test_object_operations_use_selected_blob(self):
		from core import gcs_file_storage

		blob = Mock()
		blob.download_as_bytes.return_value = b"data"
		blob.exists.return_value = True
		bucket = Mock()
		bucket.blob.return_value = blob
		doc = frappe._dict(file_url="/private/files/a.pdf")
		with (
			patch.object(gcs_file_storage, "_bucket", return_value=bucket),
			patch.object(gcs_file_storage.frappe, "conf", frappe._dict(gcs_bucket="files")),
		):
			gcs_file_storage.gcs_put_bytes("dev/private/files/a.pdf", b"data", "a.pdf")
			self.assertEqual(gcs_file_storage.gcs_get_bytes(doc), b"data")
			self.assertTrue(gcs_file_storage.gcs_head_exists(doc))
			gcs_file_storage.gcs_delete(doc)
		blob.upload_from_string.assert_called_once()
		blob.download_as_bytes.assert_called_once_with()
		blob.exists.assert_called_once_with()
		blob.delete.assert_called_once_with()


class TestFileOverrideStorageDispatch(FrappeTestCase):
	def test_get_content_dispatches_to_default_filesystem(self):
		doc = File(
			{
				"doctype": "File",
				"file_name": "a.pdf",
				"file_url": "/private/files/a.pdf",
				"is_private": 1,
			}
		)
		with (
			patch.object(doc, "_selected_cloud_backend", return_value=None),
			patch.object(FrappeFile, "get_content", return_value=b"local-data") as local_get,
			patch("core.override.file.gcs_get_bytes") as gcs_get,
			patch("core.override.file.s3_get_bytes") as s3_get,
		):
			self.assertEqual(doc.get_content(), b"local-data")
			local_get.assert_called_once_with()
			gcs_get.assert_not_called()
			s3_get.assert_not_called()

	def test_get_content_dispatches_to_gcs(self):
		doc = File(
			{
				"doctype": "File",
				"file_name": "a.pdf",
				"file_url": "/private/files/a.pdf",
				"is_private": 1,
			}
		)
		with (
			patch.object(doc, "_selected_cloud_backend", return_value="GCS"),
			patch.object(doc, "validate_file_url"),
			patch("core.override.file.gcs_get_bytes", return_value=b"gcs-data"),
			patch("core.override.file.s3_get_bytes") as s3_get,
		):
			self.assertEqual(doc.get_content(), "gcs-data")
			s3_get.assert_not_called()

	def test_get_content_preserves_s3_dispatch(self):
		doc = File(
			{
				"doctype": "File",
				"file_name": "a.pdf",
				"file_url": "/private/files/a.pdf",
				"is_private": 1,
			}
		)
		with (
			patch.object(doc, "_selected_cloud_backend", return_value="S3"),
			patch.object(doc, "validate_file_url"),
			patch("core.override.file.s3_get_bytes", return_value=b"s3-data"),
			patch("core.override.file.gcs_get_bytes") as gcs_get,
		):
			self.assertEqual(doc.get_content(), "s3-data")
			gcs_get.assert_not_called()

	def test_exists_dispatches_to_gcs(self):
		doc = File(
			{
				"doctype": "File",
				"file_name": "a.pdf",
				"file_url": "/private/files/a.pdf",
				"is_private": 1,
			}
		)
		with (
			patch.object(doc, "_selected_cloud_backend", return_value="GCS"),
			patch("core.override.file.gcs_head_exists", return_value=True) as gcs_exists,
			patch("core.override.file.s3_head_exists") as s3_exists,
		):
			self.assertTrue(doc.exists_on_disk())
			gcs_exists.assert_called_once_with(doc)
			s3_exists.assert_not_called()
