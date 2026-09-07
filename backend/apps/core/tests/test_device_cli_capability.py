import unittest
from types import SimpleNamespace

from apps.core.device_cli_capability import DeviceCliCapability, DeviceCliCapabilityError


class DeviceCliCapabilityTests(unittest.TestCase):
    def test_rejects_invalid_device_id(self) -> None:
        with self.assertRaises(DeviceCliCapabilityError):
            DeviceCliCapability.validate_device_id('../invalid')

    def test_rejects_dangerous_command(self) -> None:
        with self.assertRaises(DeviceCliCapabilityError):
            DeviceCliCapability.validate_command('sudo reboot')

    def test_accepts_read_only_command(self) -> None:
        DeviceCliCapability.validate_device_id('nvr_5003')
        DeviceCliCapability.validate_command('systemctl is-active camera-agent')

    def test_requires_device_cli_enabled_in_global_environment(self) -> None:
        with self.assertRaises(DeviceCliCapabilityError):
            DeviceCliCapability.device_settings(SimpleNamespace(runtime_settings={}))

        settings = DeviceCliCapability.device_settings(
            SimpleNamespace(runtime_settings={'device_cli': {'enabled': True}})
        )
        self.assertTrue(settings['enabled'])

    def test_requires_enabled_ssh_connection_response(self) -> None:
        with self.assertRaises(DeviceCliCapabilityError):
            DeviceCliCapability.validate_connection_response({'isOpen': False})
        with self.assertRaises(DeviceCliCapabilityError):
            DeviceCliCapability.validate_connection_response({'isOpen': True})

        self.assertEqual(
            DeviceCliCapability.validate_connection_response({'isOpen': True, 'command': 'ssh device'}),
            'ssh device',
        )