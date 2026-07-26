# -*- coding: utf-8 -*-
import json
import time
import pytest
from pprint import pprint
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.utils.data_utils import DataUtils

class TestCameraDealer:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        api_instance.login("DEALER")
        cus_param = {
                "page.total": 10,
                "page.limit": 10,
                "page.offset": 0
        }
        # get customer list
        response = api_instance.send(endpoint_path="user_customers", method="GET", params=cus_param)
        Assertions.assert_status_code(response, 200)
        rep_customer_list = json.loads(response.content)
        Assertions.assert_not_empty(rep_customer_list["data"])
        cls.org_id_0 = rep_customer_list["data"][0]["customer"]["orgId"]        
        cls.header = {
            'x-org-id': str(cls.org_id_0)
        }
        
        # get site list of customer
        response = api_instance.send(endpoint_path="site_tree", method="GET", headers=cls.header)
        Assertions.assert_status_code(response, 200)
        rep_site_list = json.loads(response.content)
        Assertions.assert_not_empty(rep_site_list["sites"])
        cls.site_id_0 = rep_site_list["sites"][0]["id"]
        cls.site_tz_0 = rep_site_list["sites"][0]["timezone"]
            
        # get nvr list of site
        nvr_param = {
            "siteId": cls.site_id_0,
            "page.limit": 10
        }
        response = api_instance.send(endpoint_path="device_nvrs", method="GET", params=nvr_param, headers=cls.header)
        Assertions.assert_status_code(response, 200)
        rep_nvr_list = json.loads(response.content)
        Assertions.assert_not_empty(rep_nvr_list["data"])
        cls.nvr_id_0 = rep_nvr_list["data"][0]["id"]
            
        # get camera list of nvr
        camera_param = {
            "siteId": cls.site_id_0,
            "nvrId": cls.nvr_id_0,
            "page.limit": 10
        }
        response = api_instance.send(endpoint_path="camera_cameras", method="GET", params=camera_param, headers=cls.header)
        Assertions.assert_status_code(response, 200)
        rep_camera_list = json.loads(response.content)
        Assertions.assert_not_empty(rep_camera_list["data"])

        cls.camera_id_0 = rep_camera_list["data"][0]["id"]
        cls.camera_name_0 = rep_camera_list["data"][0]["name"]
        for camera in rep_camera_list["data"]:
            if DataUtils.find_item_by_key(camera, key="enabled", value=True, path="cloudCapabilities.funcsEnabled.goods_unit_type_monitoring"):
                cls.camera_id_0 = camera["id"]
                cls.camera_name_0 = camera["name"]
                break
        
    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        api_instance.login("CUSTOMER")
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    def test_get_list_cameras_with_site_nvr_success(self):
        """
        GET    
        list cameras
        Success
        :param input_data:
        :return:
        """
        param = {
            'page.limit': 20,
            'siteId': self.site_id_0, 
            'nvrId': self.nvr_id_0,
            'name': ""
        }
        try:
            response = api_instance.send(endpoint_path="camera_cameras", method="GET", is_valid=True, params=param, headers=self.header)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["page"]["limit"], param["page.limit"])
            Assertions.assert_equal(rep["data"][0]["siteId"], param["siteId"])
            Assertions.assert_equal(rep["data"][0]["nvrId"], param["nvrId"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_get_list_cameras_with_invalid_format_fail(self):
        """
        GET    
        list cameras
        fail
        :param input_data:
        :return:
        """
        param = {
            'page.limit': 20,
            'siteId': self.site_id_0, 
            'nvrId': "xxxxxx",
            'name': ""
        }
        try:
            response = api_instance.send(endpoint_path="camera_cameras", method="GET", is_valid=True, params=param, headers=self.header)
            rep = json.loads(response.content)
            if isinstance(param["nvrId"], str):
                 Assertions.assert_status_code(response, 400)
                 Assertions.assert_in("invalid syntax", rep["message"])
            else:
                Assertions.assert_status_code(response, 200)
                Assertions.assert_equal(rep["page"]["limit"], param["page.limit"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        
    @pytest.mark.P0
    def test_get_list_cameras_with_name_success(self):
        """
        GET    
        list cameras
        Success
        :param input_data:
        :return:
        """
        param = {
            'page.limit': 20,
            'siteId': self.site_id_0, 
            'nvrId': self.nvr_id_0,
            'name': self.camera_name_0
        }
        try:
            response = api_instance.send(endpoint_path="camera_cameras", method="GET", is_valid=True, params=param, headers=self.header)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_true(len(rep["data"]) > 0)
            Assertions.assert_in(param["name"], rep["data"][0]["name"])

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_get_get_camera_success(self):
        """
        GET    
        list camera
        Success
        :param path_param: cameraId
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="camera_cameras_id", method="GET", is_valid=True, id=self.camera_id_0, headers=self.header)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["data"]["id"], self.camera_id_0)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("enableMonitoring", [True, False])
    @pytest.mark.parametrize("schedules", [
        [
            {
                "allYear": False,
                "allDay": True,
                "timeRanges": [],
                "weekdays": [
                    "sunday",
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday"
                ]
            }
        ],
        [
            {
                "allYear": False,
                "allDay": False,
                "timeRanges": [
                    {
                        "startedAt": 30600,
                        "endedAt": 39600
                    },
                    {
                        "startedAt": 50400,
                        "endedAt": 63000
                    }
                ],
                "weekdays": [
                    "monday",
                    "wednesday",
                    "friday"
                ]
            },
            {
                "allYear": False,
                "allDay": False,
                "timeRanges": [
                    {
                        "startedAt": 72000,
                        "endedAt": 82800
                    }
                ],
                "weekdays": [
                    "saturday",
                    "sunday"
                ]
            }
        ]
    ])
    def test_post_update_monitor_schedule_success(self, enableMonitoring, schedules):
        """
        POST    
        update monitor schedule
        Success
        :param input_data:
        :return:
        """
        input_data = {
            "camIds": [self.camera_id_0],
            "camSchedule": {
                "enableMonitoring": enableMonitoring,
                "schedules": schedules,
                "timezone": self.site_tz_0
            },
            "siteId": self.site_id_0
        }
        # set monitor schedule
        try:
            response = api_instance.send(endpoint_path="camera_cameras_monitoring_schedule", method="POST", is_valid=True, headers=self.header, data=input_data)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # check monitor schedule
        try:
            response = api_instance.send(endpoint_path="camera_cameras_id_monitoring_schedule", method="GET", is_valid=True, id=self.camera_id_0, headers=self.header)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["camConfig"]["camId"], self.camera_id_0)
            Assertions.assert_equal(rep["camConfig"]["monitorSchedule"]["enableMonitoring"], enableMonitoring)
            Assertions.assert_equal(rep["camConfig"]["monitorSchedule"]["schedules"], schedules)
            Assertions.assert_equal(rep["camConfig"]["monitorSchedule"]["timezone"], self.site_tz_0)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")