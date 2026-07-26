# -*- coding: utf-8 -*-
import json
import random
import pytest

from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker


class TestOrganization:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        response = api_instance.send(endpoint_path="site_tree", method="GET")
        Assertions.assert_status_code(response, 200)
        rep = json.loads(response.content)
        cls.siteIds = []
        Assertions.assert_not_empty(rep["sites"])
        for i in range(len(rep["sites"])):
            cls.siteIds.append(rep["sites"][i]["id"])
        print(f"show siteIds: {cls.siteIds} ")
        data = {
            "email": faker.generate_email(),
            "firstName": "API",
            "lastName": "org user test",
            "phoneNumber": faker.generate_phone_number(),
            "roleName": "org_admin"
        }
        response = api_instance.send(endpoint_path="org_users", method="POST", data=data)
        rep = json.loads(response.content)
        Assertions.assert_status_code(response, 200)
        cls.user_id = rep["data"]["user"]["id"]
        print(f"show user_id: {cls.user_id} ")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", ["viewer", "site_manager", "org_admin"])
    def test_post_add_org_user_success(self, input_data):
        """
        POST
        测试customer账号add org_user
        请求成功
        """
        try:
            data = {
                "email": faker.generate_email(),
                "firstName": "API",
                "lastName": "org user test",
                "phoneNumber": faker.generate_phone_number(),
                "roleName": input_data
            }
            if input_data == "site_manager":
                data["siteIds"] = random.sample(self.siteIds, 1)
            response = api_instance.send(endpoint_path="org_users", method="POST", data=data, is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            user_id = rep["data"]["user"]["id"]
            Assertions.assert_equal(rep["data"]["user"]["email"], data["email"])
            Assertions.assert_equal(rep["data"]["user"]["firstName"], data["firstName"])
            Assertions.assert_equal(rep["data"]["user"]["lastName"], data["lastName"])
            Assertions.assert_equal(rep["data"]["user"]["phoneNumber"], data["phoneNumber"])
            Assertions.assert_equal(rep["data"]["user"]["role"]["name"], data["roleName"])
            if data["roleName"] == "site_manager":
                Assertions.assert_equal_sorted(rep["data"]["siteIds"], data["siteIds"])

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        finally:
            response2 = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id)
            response2.raise_for_status()

    @pytest.mark.P0
    def test_delete_delete_org_user_success(self):
        """
        DELETE
        测试customer账号delete org_user
        请求成功
        """
        try:
            # 新增user
            data = {
                "email": faker.generate_email(),
                "roleName": "org_admin"
            }
            response = api_instance.send(endpoint_path="org_users", method="POST", data=data)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            user_id = rep["data"]["user"]["id"]

            # 删除user
            response2 = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id, is_valid=True)
            Assertions.assert_status_code(response2, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data, expected", [
        (faker.generate_email(), "email"),
        ("123666667999", "phoneNumber"),
        ("org api update", "firstName"),
        ("123666667999", "lastName"),
        ("site_manager", "roleName"),
        ("org_admin", "roleName"),
    ])
    def test_patch_update_org_user_success(self, input_data, expected):
        """
        PATCH
        测试customer账号update org_user
        请求成功
        """
        try:
            data = {
                expected: input_data
            }
            if input_data == "site_manager":
                data["siteIds"] = random.sample(self.siteIds, 1)
            response = api_instance.send(endpoint_path="org_users_id", method="PATCH", data=data, id=self.user_id,
                                         is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if expected == "roleName":
                Assertions.assert_equal(rep["data"]["user"]["role"]["name"], input_data)
            else:
                Assertions.assert_equal(rep["data"]["user"][expected], input_data)
            if input_data == "site_manager":
                Assertions.assert_equal_sorted(rep["data"]["siteIds"], data["siteIds"])

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.smoke
    @pytest.mark.P0
    def test_get_org_user_by_id_success(self):
        """
        GET
        测试customer账号get org_user by id
        请求成功
        """
        try:
            response = api_instance.send(endpoint_path="org_users_id", method="GET", id=self.user_id,
                                         is_valid=True)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
        {
            'name': None,
            'page.total': None,
            'page.limit': None,
            'page.offset': None
        },
        {
            'name': "",
            'page.total': None,
            'page.limit': None,
            'page.offset': None
        },
        {
            'name': "Test",
            'page.total': None,
            'page.limit': None,
            'page.offset': None
        },
        {
            'name': None,
            'page.total': None,
            'page.limit': 1,
            'page.offset': None
        },
        {
            'name': "Test",
            'page.total': None,
            'page.limit': 1,
            'page.offset': None
        },
        {
            'name': None,
            'page.total': None,
            'page.limit': None,
            'page.offset': 999999999
        },
        {
            'name': "Test",
            'page.total': None,
            'page.limit': 999999999999999999999999999999999999999,
            'page.offset': None
        }
        ,
        {
            'name': "Test",
            'page.total': None,
            'page.limit': None,
            'page.offset': 999999999999999999999999999999999999999
        }
    ])
    def test_get_org_user_list_success(self, input_data):
        """
        GET
        测试dealer账号获取org user list
        请求成功
        :param input_data:
        :return:
        """
        response = api_instance.send(endpoint_path="org_users", method="GET", params=input_data, is_valid=True)
        rep = json.loads(response.content)
        if response.status_code == 200:
            if input_data["page.limit"]:
                Assertions.assert_equal(rep["page"]["limit"], input_data["page.limit"])
                if len(rep["data"]) > 0:
                    Assertions.assert_equal(len(rep["data"]), input_data["page.limit"])
            if input_data["page.offset"]:
                Assertions.assert_equal(rep["page"]["offset"], input_data["page.offset"])
            if input_data["name"] and len(rep["data"]) > 0:
                Assertions.assert_in(input_data["name"].lower(), rep["data"][0]["user"]["email"])
        elif response.status_code == 400:
            Assertions.assert_equal(rep["statusCode"], "InvalidArgument")

    @pytest.mark.P1
    def test_post_org_user_activate_email_success(self):
        """
        POST
        测试dealer账号激活org user send activate_email
        请求成功
        :return:
        """
        response = api_instance.send(endpoint_path="org_users_send_activate_email", method="POST",
                                     data={"userId": self.user_id}, is_valid=True)
        Assertions.assert_status_code(response, 200)
