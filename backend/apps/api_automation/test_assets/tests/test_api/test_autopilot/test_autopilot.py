# -*- coding: utf-8 -*-
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions

class TestAutoPilot:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        #TODO prepare test data of alert and assert more
        print("\nSetting up TestAPI class...")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
        {
            "camNum": 9,
            "alertRangeMinutes": 10
        },
        {
            "camNum": 16,
            "alertRangeMinutes": 0
        }
    ])
    def test_get_autopilot_success(self, input_data):
        """
        GET camera_cameras_recent_alerted
        success
        :param
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="camera_cameras_recent_alerted", method="GET", is_valid=True, params=input_data)
            Assertions.assert_status_code(response, 200)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")