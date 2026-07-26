# -*- coding: utf-8 -*-
import json
import os
import yaml
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker
from src.core.config import config

class TestCustomer:

    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        cls.customerOrgId = api_instance.current_auth_info.org_id
        cls.customer = api_instance.dealer_data["customers"]["customer"]
        api_instance.login("DEALER")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")
        api_instance.login("CUSTOMER")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
        {
            'name': "test",
            'page.total': None,
            'page.limit': 1,
            'page.offset': 0
        },
        {
            'name': "",
            'page.total': None,
            'page.limit': 1,
            'page.offset': 2
        },
        {
            'name': "",
            'page.total': None,
            'page.limit': 20,
            'page.offset': 1
        }
    ])
    def test_get_customer_list_success(self, input_data):
        """
        GET
        测试dealer账号获取customer列表
        请求成功
        :param input_data:
        :return:
        """
        response = api_instance.send(endpoint_path="user_customers", method="GET", params=input_data, is_valid=True)
        rep = json.loads(response.content)
        Assertions.assert_status_code(response, 200)
        if rep["data"]:
            Assertions.assert_equal(rep["page"]["limit"], input_data["page.limit"])
            Assertions.assert_equal(rep["page"]["offset"], input_data["page.offset"])
        else:
            Assertions.assert_true(rep["page"]["limit"] >= 0)
            Assertions.assert_true(rep["page"]["offset"] >= 0)
        if input_data["name"] and rep["data"]:
            Assertions.assert_in(input_data["name"], rep["data"][0]["customer"]["user"]["email"])

    @pytest.mark.smoke
    @pytest.mark.P0
    def test_post_add_customer_success(self):
        """
        POST
        测试dealer账号add customer
        请求成功
        """
        org_id = 0
        try:
            data = {
                "accountName": faker.generate_name(),
                "email": faker.generate_email(),
                "phoneNumber": faker.generate_phone_number(),
                "firstName": "API",
                "lastName": "test",
            }
            response = api_instance.send(endpoint_path="user_customers", method="POST", data=data, is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            org_id = rep["data"]["user"]["organization"]["id"]
            Assertions.assert_equal(rep["data"]["user"]["email"], data["email"])
            Assertions.assert_equal(rep["data"]["user"]["firstName"], data["firstName"])
            Assertions.assert_equal(rep["data"]["user"]["lastName"], data["lastName"])
            Assertions.assert_equal(rep["data"]["user"]["phoneNumber"], data["phoneNumber"])
            Assertions.assert_equal(rep["data"]["accountName"], data["accountName"])

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        finally:
            response3 = api_instance.send(endpoint_path="user_customers_id", method="DELETE", id=org_id)
            response3.raise_for_status()

    @pytest.mark.P1
    def test_post_add_customer_repeat_400(self):
        """
        POST
        add customer repeat  400
        请求失败
        """
        org_id = 0
        try:
            data = {
                "accountName": faker.generate_name(),
                "email": faker.generate_email(),
                "phoneNumber": faker.generate_phone_number(),
                "firstName": "API",
                "lastName": "test",
            }
            response = api_instance.send(endpoint_path="user_customers", method="POST", data=data)
            response.raise_for_status()
            rep = json.loads(response.content)
            org_id = rep["data"]["user"]["organization"]["id"]
            response2 = api_instance.send(endpoint_path="user_customers", method="POST", data=data)
            rep2 = json.loads(response2.content)
            Assertions.assert_status_code(response2, 400)
            Assertions.assert_equal(rep2["message"], "account name conflict")

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        finally:
            response3 = api_instance.send(endpoint_path="user_customers_id", method="DELETE", id=org_id)
            response3.raise_for_status()

    @pytest.mark.P0
    def test_delete_customer_success(self):
        """
        DELETE
        delete customer
        请求成功
        """
        org_id = 0
        try:
            # 1.新增customer账户
            data = {
                "accountName": faker.generate_name(),
                "email": faker.generate_email(),
                "phoneNumber": faker.generate_phone_number()
            }
            response = api_instance.send(endpoint_path="user_customers", method="POST", data=data)
            response.raise_for_status()
            rep = json.loads(response.content)
            org_id = rep["data"]["user"]["organization"]["id"]
            # 2.删除customer账户
            response2 = api_instance.send(endpoint_path="user_customers_id", method="DELETE", id=org_id, is_valid=True)
            Assertions.assert_status_code(response2, 200)
            # 3.查询customer账户是否还存在
            params = {
                'name': data.get("accountName", "")
            }
            response3 = api_instance.send(endpoint_path="user_customers", method="GET", params=params)
            rep3 = json.loads(response3.content)
            response.raise_for_status()
            Assertions.assert_empty(rep3["data"])

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [{'page.limit': 1,
                                             'page.offset': 0,
                                             'page.total': 0,
                                             'siteId': None,
                                             'deviceId': None,
                                             'ordering.by': None,
                                             'ordering.order': "asc"
                                             }])
    def test_get_nvr_list_success(self, input_data):
        """
        GET    site tree
        请求成功
        :param input_data
        :return:
        """
        try:
            # 查询site
            api_instance.set_default_header("x-org-id", str(self.customerOrgId))
            response = api_instance.send(endpoint_path="device_nvrs", method="GET", is_valid=True, params=input_data)
            # schema validation would be failed with "ordering is null" if there is no data in the response
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
