# -*- coding: utf-8 -*-
import pytest
from src.api.ws_client import create_websocket_client, WebSocketRequest
from src.core.api_exceptions import RequestError

from src.data.params import WEBSOCKET_PARAMS
from src.api.client import api_instance
from src.utils.assertions import Assertions
from src.utils.data_utils import DataUtils


async def _verify_camera_rules(data, camera_id: int):
    """验证摄像头规则配置

    Args:
        data: 请求数据
        camera_id: 摄像头ID
    """
    try:
        site_id = api_instance.dealer_data["sites"]["id"]
        params = {
            "siteId": int(site_id),
            "page.limit": 100
        }
        response = api_instance.send(
            endpoint_path="alert_rules_camera",
            method="GET",
            params=params,
            is_valid=True
        )
        Assertions.assert_status_code(response, 200)

        # 从响应中找到对应摄像头的规则
        camera_list = response.json().get("data", [])
        camera_rules = DataUtils.find_item_by_key(data=camera_list, key="cameraId", value=camera_id)

        if not camera_rules:
            raise ValueError(f"No rules found for camera ID: {camera_id}")

        # 验证规则具体内容
        expected_rule = data["alertUpdateCameraRule"]["data"][0]
        Assertions.assert_deep_equal_unordered(expected_rule["algorithms"], camera_rules["algorithms"])
        Assertions.assert_deep_equal_unordered(expected_rule["actions"], camera_rules["actions"])
        Assertions.assert_deep_equal_unordered(expected_rule["schedules"], camera_rules["schedules"])
        Assertions.assert_deep_equal_unordered(expected_rule["note"], camera_rules["note"])
        #
    except Exception as e:
        raise RequestError(f"Failed to verify camera rules: {str(e)}")


class TestWSAutomation:

    @pytest.mark.P1
    @pytest.mark.asyncio
    async def test_ws_alert_update_camera_rules_schedules(self):
        websocket_instance = await create_websocket_client()
        data = WEBSOCKET_PARAMS["alertUpdateCameraRule_schedules"]
        camera = DataUtils.find_item_by_key(data=api_instance.dealer_data["cameras"], key="sip", value=True, return_parent=True)
        if camera:
            data["alertUpdateCameraRule"]["data"][0]["cameraId"] = camera.get("id")
        else:
            raise ValueError("Camera with the specified serial number not found.")
        request_data = WebSocketRequest.create(data)
        response = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        expected_values = {
            'result': {
                'id': request_data["request"]["id"],
                'act': 'alert.update_camera_alert_rules.reply',
                'data': {
                    'alertUpdateCameraRuleReply': {
                        'result': [
                            {'cameraId': camera.get("id"), 'error': None}
                        ]
                    }
                }
            }
        }
        Assertions.check_ws_response_data(response, expected_values)

        # 验证规则配置
        await _verify_camera_rules(data, camera.get("id"))

    @pytest.mark.P1
    @pytest.mark.asyncio
    async def test_ws_alert_update_camera_rules_intrusion(self):

        websocket_instance = await create_websocket_client()
        data = WEBSOCKET_PARAMS["alertUpdateCameraRule_intrusion"]
        camera = DataUtils.find_item_by_key(data=api_instance.dealer_data["cameras"], key="supportCrossLine", value=True, return_parent=True)
        if camera:
            data["alertUpdateCameraRule"]["data"][0]["cameraId"] = camera.get("id")
        else:
            raise ValueError("Camera with the specified serial number not found.")
        request_data = WebSocketRequest.create(data)
        response = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        expected_values = {
            'result': {
                'id': request_data["request"]["id"],
                'act': 'alert.update_camera_alert_rules.reply',
                'data': {
                    'alertUpdateCameraRuleReply': {
                        'result': [
                            {'cameraId': camera.get("id"), 'error': None}
                        ]
                    }
                }
            }
        }
        Assertions.check_ws_response_data(response, expected_values)
        # 验证规则配置
        await _verify_camera_rules(data, camera.get("id"))

    @pytest.mark.P1
    @pytest.mark.asyncio
    async def test_ws_alert_update_camera_rules_crossline(self):

        websocket_instance = await create_websocket_client()
        data = WEBSOCKET_PARAMS["alertUpdateCameraRule_crossline"]
        camera = DataUtils.find_item_by_key(data=api_instance.dealer_data["cameras"], key="supportCrossLine", value=True, return_parent=True)
        if camera:
            data["alertUpdateCameraRule"]["data"][0]["cameraId"] = camera.get("id")
        else:
            raise ValueError("Camera with the specified serial number not found.")
        request_data = WebSocketRequest.create(data)
        response = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        expected_values = {
            'result': {
                'id': request_data["request"]["id"],
                'act': 'alert.update_camera_alert_rules.reply',
                'data': {
                    'alertUpdateCameraRuleReply': {
                        'result': [
                            {'cameraId': camera.get("id"), 'error': None}
                        ]
                    }
                }
            }
        }
        Assertions.check_ws_response_data(response, expected_values)
        # 验证规则配置
        await _verify_camera_rules(data, camera.get("id"))

    @pytest.mark.P1
    @pytest.mark.asyncio
    async def test_ws_alert_update_camera_rules_other(self):

        websocket_instance = await create_websocket_client()
        data = WEBSOCKET_PARAMS["alertUpdateCameraRule_other"]
        camera = DataUtils.find_item_by_key(data=api_instance.dealer_data["cameras"], key="supportCrossLine", value=True, return_parent=True)
        if camera:
            data["alertUpdateCameraRule"]["data"][0]["cameraId"] = camera.get("id")
        else:
            raise ValueError("Camera with the specified serial number not found.")
        request_data = WebSocketRequest.create(data)
        response = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        expected_values = {
            'result': {
                'id': request_data["request"]["id"],
                'act': 'alert.update_camera_alert_rules.reply',
                'data': {
                    'alertUpdateCameraRuleReply': {
                        'result': [
                            {'cameraId': camera.get("id"), 'error': None}
                        ]
                    }
                }
            }
        }
        Assertions.check_ws_response_data(response, expected_values)
        # 验证规则配置
        await _verify_camera_rules(data, camera.get("id"))

