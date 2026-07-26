# -*- coding: utf-8 -*-
import json
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions

class TestCameraCustomer:     
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        api_instance.login("DEALER")
        print("\nPrepare preconditions...")
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
        org_id_0 = rep_customer_list["data"][0]["customer"]["orgId"]        
        cls.header = {
            'x-org-id': str(org_id_0)
        }
        
        # get site list of customer
        response = api_instance.send(endpoint_path="site_tree", method="GET", headers=cls.header)
        Assertions.assert_status_code(response, 200)
        rep_site_list = json.loads(response.content)
        Assertions.assert_not_empty(rep_site_list["sites"])
        cls.site_id_0 = rep_site_list["sites"][0]["id"]
            
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
       
        # restore the default role
        api_instance.login("CUSTOMER")
       
    @pytest.mark.P0
    def test_get_list_cameras_success(self):
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
            'nvrId': self.nvr_id_0
        }
        try:
            response = api_instance.send(endpoint_path="camera_cameras", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["page"]["limit"], param["page.limit"])

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
            response = api_instance.send(endpoint_path="camera_cameras_id", method="GET", is_valid=True, id=self.camera_id_0)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["data"]["id"], self.camera_id_0)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}") 