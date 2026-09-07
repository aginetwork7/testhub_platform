import unittest

from apps.ai_testing.execution.capabilities import (
    get_capability,
    validate_browser_action,
    validate_capability_arguments,
)


class CapabilityRegistryTests(unittest.TestCase):
    def test_browser_navigation_declares_url_evidence(self) -> None:
        capability = get_capability('browser.navigate')

        self.assertEqual(capability.evidence_types, ('url_snapshot',))
        self.assertEqual(capability.assertion_kinds, ('url',))

    def test_rejects_unknown_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, 'Unsupported capability'):
            get_capability('browser.open_camera_page')

    def test_requires_declared_arguments(self) -> None:
        with self.assertRaisesRegex(ValueError, 'missing arguments: url'):
            validate_capability_arguments('browser.navigate', {})

    def test_requires_inspection_capability_for_assertions(self) -> None:
        with self.assertRaisesRegex(ValueError, 'requires capability browser.inspect'):
            validate_browser_action('assert', ['browser.act'])