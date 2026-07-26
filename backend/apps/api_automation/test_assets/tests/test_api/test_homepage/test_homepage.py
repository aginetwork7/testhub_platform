# -*- coding: utf-8 -*-
import pytest
import json
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions

class TestAutoPilot:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        try:
            stats_info = api_instance.dealer_data["customers"]["stats"]
            cls.siteNum = int(stats_info["siteNum"])
            cls.camNum = int(stats_info["camNum"])
            cls.onlineCamNum = int(stats_info["onlineCamNum"])
            cls.offlineCamNum = int(stats_info["offlineCamNum"])
            cls.dealer_email = api_instance.dealer_data["dealer"]["email"]
        except Exception as e:
            KeyError(f"dealer_data was not fully populated: {str(e)}")
            raise
        print("\nSetting up TestAPI class...")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    def test_get_get_header_success(self):
        """
        GET stats_header
        success
        :param
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="stats_header", method="GET", is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["stats"]["siteNum"], self.siteNum)
            Assertions.assert_equal(rep["stats"]["camNum"], self.camNum)
            Assertions.assert_equal(rep["stats"]["onlineCamNum"], self.onlineCamNum)
            Assertions.assert_equal(rep["stats"]["offlineCamNum"], self.offlineCamNum)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_get_get_dealer_info_success(self):
        """
        GET org_dealer
        success
        :param
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="org_dealer", method="GET", is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["company"]["email"], self.dealer_email)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")