from django.test import SimpleTestCase

from apps.ai_testing.global_planner import GlobalPlanError, GlobalTestPlanner


class GlobalTestPlannerTests(SimpleTestCase):
    def test_normalize_response_supports_ordered_browser_and_device_steps(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': (
                        '{"steps":[{"executor":"device_cli","description":"检查设备服务",'
                        '"device_id":"ainvr_5000"},{"executor":"browser",'
                        '"description":"确认设备在线"}]}'
                    ),
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=7,
            task_description='检查 ainvr_5000 并确认设备在线',
        )

        self.assertEqual(steps[0]['executor'], 'device_cli')
        self.assertEqual(steps[0]['device_id'], 'ainvr_5000')
        self.assertEqual(steps[1]['executor'], 'browser')
        self.assertEqual(steps[1]['step_mode'], 'ai')

    def test_normalize_response_rejects_device_step_without_environment(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查设备","device_id":"ainvr_5000"}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '未选择设备 CLI 环境'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=None,
                task_description='检查 ainvr_5000',
            )

    def test_normalize_response_rejects_device_id_not_in_user_goal(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查设备","device_id":"5"}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '未在原始需求中明确出现'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=5,
                task_description='连接 ainvr_5000 并检查服务状态',
            )

    def test_normalize_response_keeps_embedded_device_process_command(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查 manager 进程","device_id":"nvr_5003","command":"ps | grep \'[m]anager\'"}]}',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='连接 nvr_5003，使用 ps 检查 manager 进程是否存在',
        )

        self.assertEqual(steps[0]['command'], "ps | grep '[m]anager'")

    def test_normalize_response_routes_event_construction_to_data_factory(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"data_factory","action":"report_vehicle_event","description":"上报车辆事件","camera_name":"5003_D13"}]}',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='在 test-2 环境为摄像头 5003_D13 通过事件构造工具产生真实 Vehicle 事件',
        )

        self.assertEqual(steps[0]['executor'], 'data_factory')
        self.assertEqual(steps[0]['camera_name'], '5003_D13')

    def test_normalize_response_rewrites_browser_event_construction(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"browser","description":"使用事件构造工具产生真实 Vehicle 事件，并在 Alert 页面验证"}]}',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='为摄像头 5003_D13 通过事件构造工具产生真实 Vehicle 事件，并在 Alert 页面验证',
        )

        self.assertEqual([step['executor'] for step in steps], ['data_factory', 'browser'])
        self.assertEqual(steps[0]['camera_name'], '5003_D13')