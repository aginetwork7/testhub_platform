from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai_testing.execution.environment_resources import (
    default_device_camera_names,
    default_device_site,
    environment_device_resources,
    is_text_input,
    refers_to_target_device,
)


def _configuration(**edge):
    return SimpleNamespace(runtime_settings={'api': {'edge': edge}})


class EnvironmentDeviceResourceTests(SimpleTestCase):
    def test_configured_devices_become_resources_main_device_first(self) -> None:
        configuration = _configuration(
            backup_device={'device_id': 'nvr_10005', 'cameras': [{'camera_mac': 'aa', 'camera_name': '打包区1'}]},
            main_device={'device_id': 'nvr_5003', 'cameras': [{'camera_mac': 'bb', 'camera_name': '5003_D13'}]},
        )

        resources = environment_device_resources(configuration)

        self.assertEqual([r['resource']['role'] for r in resources], ['main_device', 'backup_device'])
        self.assertEqual(resources[0]['resource_type'], 'environment_device')
        self.assertEqual(resources[0]['resource_id'], 'nvr_5003')
        self.assertEqual(resources[0]['resource']['camera_names'], ['5003_D13'])
        self.assertEqual(resources[0]['resource']['result_correlation'], {'match_values': ['5003_D13']})
        self.assertNotIn('camera_mac', str(resources))
        self.assertEqual(default_device_camera_names(resources), ['5003_D13'])

    def test_missing_configuration_yields_nothing(self) -> None:
        self.assertEqual(environment_device_resources(None), [])
        self.assertEqual(environment_device_resources(SimpleNamespace(runtime_settings={})), [])
        self.assertEqual(environment_device_resources(SimpleNamespace(runtime_settings={'api': {'edge': {'main_device': {}}}})), [])
        self.assertEqual(default_device_camera_names([]), [])

    def test_backup_device_is_used_only_without_a_main_device(self) -> None:
        resources = environment_device_resources(_configuration(backup_device={'device_id': 'nvr_1', 'cameras': [{'camera_name': 'B1'}]}))

        self.assertEqual(default_device_camera_names(resources), ['B1'])

    def test_target_device_wording_is_recognised(self) -> None:
        self.assertTrue(refers_to_target_device('Open the cameras list and locate the camera for the default test device'))
        self.assertTrue(refers_to_target_device('Click the target camera thumbnail to open the live view'))
        self.assertTrue(refers_to_target_device('点击目标camera的缩略图'))
        self.assertTrue(refers_to_target_device('找到默认测试设备中的camera'))
        self.assertFalse(refers_to_target_device('Click the preview image of the first online camera in the camera list'))
        self.assertFalse(refers_to_target_device(''))
        # A step that names a configured camera is about that camera even without the words default/target.
        self.assertTrue(refers_to_target_device('Type the site name 萧山区, then locate camera 5003_D13 among the results', ['5003_D13']))
        self.assertFalse(refers_to_target_device('Type the site name 萧山区, then locate camera 5003_D13', ['5028/D1']))

    def test_optional_site_is_published_and_inputs_are_not_items(self) -> None:
        resources = environment_device_resources(_configuration(main_device={'device_id': 'nvr_5003', 'site': '萧山区', 'cameras': [{'camera_name': '5003_D13'}]}))

        self.assertEqual(resources[0]['resource']['site'], '萧山区')
        self.assertIn('萧山区', resources[0]['resource']['description'])
        self.assertEqual(default_device_site(resources), '萧山区')
        self.assertEqual(default_device_site(environment_device_resources(_configuration(main_device={'device_id': 'nvr_1', 'cameras': []}))), '')
        self.assertTrue(is_text_input({'tag': 'input', 'name': '5003_D13'}))
        self.assertTrue(is_text_input({'tag': 'div', 'role': 'textbox', 'editable': True}))
        self.assertFalse(is_text_input({'tag': 'div', 'role': 'button', 'editable': True}))
        self.assertFalse(is_text_input({'tag': 'div', 'name': '5003_D13'}))


class TextInputPredicateTests(SimpleTestCase):
    def test_only_form_fields_count_as_text_inputs(self) -> None:
        from apps.ai_testing.execution.environment_resources import is_text_input

        # Discovery flags every non-disabled element as editable; a camera card is not a text input.
        self.assertFalse(is_text_input({'tag': 'div', 'role': 'button', 'name': '5003_D13', 'editable': True}))
        self.assertFalse(is_text_input({'tag': 'button', 'editable': True}))
        self.assertTrue(is_text_input({'tag': 'input', 'editable': True}))
        self.assertTrue(is_text_input({'tag': 'textarea'}))
        self.assertTrue(is_text_input({'tag': 'select'}))
        self.assertTrue(is_text_input({'tag': 'div', 'role': 'textbox'}))
        self.assertTrue(is_text_input({'tag': 'div', 'role': 'searchbox'}))
