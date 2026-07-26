# -*- coding: utf-8 -*-
import json
import time
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker


class TestAutomation:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""

    @pytest.mark.P0
    def test_am_get_site_list_success(self):
        """
        GET    site tree
        请求成功
        :return:
        """
        try:
            # 查询site
            response = api_instance.send(endpoint_path="site_tree", method="GET", is_valid=True)
            Assertions.assert_status_code(response, 200)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_am_get_camera_rule_list_success(self):
        """
        GET    camera rules
        请求成功
        :return:
        """
        try:
            siteId = api_instance.dealer_data["sites"]["id"]
            params = {
                "siteId": int(siteId),
                "page.limit": 100
            }
            response = api_instance.send(endpoint_path="alert_rules_camera", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
