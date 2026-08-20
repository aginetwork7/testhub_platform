from base64 import b64encode
from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.api_automation.models import ApiAutomationConfiguration
from apps.api_automation.serializers import ApiAutomationConfigurationSerializer


class ApiAutomationConfigurationDeviceKeyTests(TestCase):
    def setUp(self) -> None:
        self.configuration = ApiAutomationConfiguration.objects.create(
            name='Device Key Environment',
            environment='device-key',
        )

    def test_device_keys_are_encrypted_and_not_serialized(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        encoded_key = b64encode(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ).decode('utf-8')

        serializer = ApiAutomationConfigurationSerializer(
            self.configuration,
            data={'main_device_key': encoded_key},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.configuration.refresh_from_db()
        serialized = ApiAutomationConfigurationSerializer(self.configuration).data

        self.assertEqual(self.configuration.get_event_device_key('main'), encoded_key)
        self.assertNotEqual(self.configuration.event_device_keys_encrypted, encoded_key)
        self.assertTrue(serialized['has_main_device_key'])
        self.assertNotIn('main_device_key', serialized)
        self.assertNotIn('event_device_keys_encrypted', serialized)

    def test_migration_command_imports_legacy_environment_keys(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / '.env.device-key'
            environment_file.write_text('MAIN_KEY=legacy-main\nBACKUP_KEY=legacy-backup\n', encoding='utf-8')

            output = StringIO()
            call_command(
                'migrate_api_automation_device_keys',
                '--env-dir', temporary_directory,
                stdout=output,
            )

        self.configuration.refresh_from_db()
        self.assertEqual(self.configuration.get_event_device_key('main'), 'legacy-main')
        self.assertEqual(self.configuration.get_event_device_key('backup'), 'legacy-backup')