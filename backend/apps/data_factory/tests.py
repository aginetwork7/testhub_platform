from django.test import TestCase

from apps.data_factory.tools.business_tools import BusinessTools

class ConstructAlertEventTests(TestCase):
	def test_constructs_person_event_with_selected_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(rule_type=1)

		rule_info = result['result']['event']['raw']['struct']['StructureInfo']['ObjInfo']['PersonInfoList'][0]['RuleInfo']

		self.assertTrue(result['success'])
		self.assertEqual(rule_info, {'PointList': None, 'PointNum': 0, 'RuleType': 1, 'TriggerType': 0})

	def test_constructs_vehicle_event_with_selected_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(alert_type='vehicle', rule_type=3)

		rule_info = result['result']['event']['raw']['struct']['StructureInfo']['ObjInfo']['VehicleInfoList'][0]['RuleInfo']

		self.assertTrue(result['success'])
		self.assertEqual(rule_info, {'PointList': None, 'PointNum': 0, 'RuleType': 3, 'TriggerType': 0})

	def test_rejects_unsupported_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(rule_type=4)

		self.assertFalse(result['success'])
		self.assertIn('规则类型', result['error'])

