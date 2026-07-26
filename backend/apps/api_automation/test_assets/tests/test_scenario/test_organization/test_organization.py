# -*- coding: utf-8 -*-
import json
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker
from src.utils.data_utils import DataUtils

class TestOrganization:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        customer_info = api_instance.dealer_data.get("customers", {}).get("customer", {})
        site_info = api_instance.dealer_data.get("sites", {})
        cls.orgId = customer_info.get("orgId", None)
        cls.accountName = customer_info.get("accountName", "")
        cls.siteId = site_info.get("id", None) 
        api_instance.login("DEALER")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        api_instance.login("CUSTOMER")
        print("\nTearing down TestAPI class...")

    def check_response_of_user_role(self, rep, user_data):
        Assertions.assert_equal(rep["data"]["user"]["email"], user_data["email"])
        Assertions.assert_equal(rep["data"]["user"]["firstName"], user_data["firstName"])
        Assertions.assert_equal(rep["data"]["user"]["lastName"], user_data["lastName"])
        Assertions.assert_equal(rep["data"]["user"]["phoneNumber"], user_data["phoneNumber"])
        Assertions.assert_equal(rep["data"]["user"]["role"]["name"], user_data["roleName"])
        if user_data["roleName"] == "project_manager":
            res = DataUtils.find_item_by_key(data=rep["data"]["customers"], key="orgId", value=self.orgId)
            Assertions.assert_not_equal(res, None)
        if user_data["roleName"] == "guard":
            Assertions.assert_equal_sorted(rep["data"]["orgToSiteList"], user_data["orgToSiteList"])

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", ["dealer_admin", "dealer_rep", "project_manager", "technician", "inspector", "dispatcher", "operator", "guard"])
    def test_org_user_role_add_update_get_delete(self, input_data):
        """
        测试 org_user role add update get delete
        steps:
        1. add org_user
        2. get org_user by id
        3. update org_user
        4. get org_user by id
        5. delete org_user
        6. check org_users
        """
        user_data = {
            "email": faker.generate_email(),
            "firstName": "API",
            "lastName": "org user test",
            "phoneNumber": faker.generate_phone_number(),
            "roleName": input_data,
            "customers": [],
            "siteIds": [],
            "orgToSiteList": []
        }
        # add org_user
        try:
            if input_data == "project_manager":
                user_data["customers"] = [{"orgId": self.orgId, "accountName": self.accountName}]
            if input_data == "guard":
                user_data["orgToSiteList"] = [{"orgId": self.orgId, "siteIdList": [self.siteId]}]
            response = api_instance.send(endpoint_path="org_users", method="POST", data=user_data, is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            user_id = rep.get("data", {}).get("user", {}).get("id", None)
            Assertions.assert_is_instance(user_id, int)
            self.check_response_of_user_role(rep, user_data)

        except Exception as e:
            response = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id, is_valid=True)
            raise RequestError(f"Error while add user: {str(e)}")

        # get org user by id
        try:
            response = api_instance.send(endpoint_path="org_users_id", method="GET", id=user_id, is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            self.check_response_of_user_role(rep, user_data)
        except Exception as e:
            response = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id, is_valid=True)
            raise RequestError(f"Error while get user by id {user_id}: {str(e)}")

        # update org_user
        try:
            update_data = {
                "email": faker.generate_email(),
                "firstName": "API update",
                "lastName": "org user test update",
                "phoneNumber": faker.generate_phone_number(),
                "roleName": input_data
            }
            if input_data == "project_manager":
                update_data["customers"] = [{"orgId": self.orgId, "accountName": self.accountName}]
            if input_data == "guard":
                update_data["orgToSiteList"] = []
            response = api_instance.send(endpoint_path=f"org_users_id", method="PATCH", id=user_id, data=update_data, is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            self.check_response_of_user_role(rep, update_data)
        except Exception as e:
            response = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id, is_valid=True)
            raise RequestError(f"Error while update user by id {user_id}: {str(e)}")

        # delete org_user
        try:
            response = api_instance.send(endpoint_path="org_users_id", method="DELETE", id=user_id, is_valid=True)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"Error while delete user by id {user_id}: {str(e)}")

        # check org_users
        try:
            response = api_instance.send(endpoint_path="org_users", method="GET", is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            res = DataUtils.find_item_by_key(data=rep["data"], key="id", value=user_id)
            Assertions.assert_equal(res, None)
        except RequestError as e:
            raise RequestError(f"Error while get users: {str(e)}")
        except AssertionError as e:
            raise AssertionError(f"Error while check deleted user {user_id}: {str(e)}")