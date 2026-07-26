# -*- coding: utf-8 -*-
import json
import time
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker
from src.utils.data_utils import DataUtils


class TestSite:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        # 添加customer账户
        api_instance.login("DEALER")
        data = {
            "accountName": faker.generate_name(),
            "email": faker.generate_email(),
            "phoneNumber": faker.generate_phone_number()
        }
        response = api_instance.send(endpoint_path="user_customers", method="POST", data=data)
        response.raise_for_status()
        rep = json.loads(response.content)
        cls.org_id = rep["data"]["user"]["organization"]["id"]
        cls.headers = {
            'x-org-id': str(cls.org_id)
        }
        print(f"show org_id: {cls.org_id}")
        # 添加site
        data2 = {
            "site": {
                "name": faker.generate_name(),
                "timezone": faker.generate_timezone()
            }
        }
        response2 = api_instance.send(endpoint_path="site_sites", method="POST", headers=cls.headers, data=data2)
        response2.raise_for_status()
        rep2 = json.loads(response2.content)
        cls.site_id = rep2["id"]
        print(f"show site_id: {cls.site_id}")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")
        # 删除site
        response2 = api_instance.send(endpoint_path="site_sites_id", method="DELETE", id=cls.site_id, headers=cls.headers)
        response2.raise_for_status()
        print(f"delete site_id: {cls.site_id}")
        # 删除customer账户
        response = api_instance.send(endpoint_path="user_customers_id", method="DELETE", id=cls.org_id)
        response.raise_for_status()
        api_instance.login("CUSTOMER")
        print(f"delete org_id: {cls.org_id}")

    @pytest.mark.P0
    def test_post_add_site_success(self):
        """
        POST
        add site
        请求成功
        """
        site_id = 0
        try:
            # 新增site
            data = {
                "site": {
                    "details": {
                        "address": faker.generate_address(),
                        "city": faker.generate_city(),
                        "state": faker.generate_state(),
                        "zipcode": faker.generate_zipcode()
                    },
                    "name": faker.generate_name(),
                    "timezone": faker.generate_timezone()
                }
            }
            response = api_instance.send(endpoint_path="site_sites", method="POST", headers=self.headers,
                                         data=data, is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            site_id = rep["id"]

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        finally:
            # 删除site
            response2 = api_instance.send(endpoint_path="site_sites_id", method="DELETE", id=site_id, headers=self.headers)
            response2.raise_for_status()

    @pytest.mark.smoke
    @pytest.mark.P0
    def test_put_update_site_success(self):
        """
        PUT
        update site
        请求成功
        """
        try:
            # 修改site
            data = {
                "data": {
                    "details": {
                        "address": faker.generate_address(),
                        "city": faker.generate_city(),
                        "state": faker.generate_state(),
                        "zipcode": faker.generate_zipcode(),
                        "polygon": [
                            {
                                "latitude": int(faker.generate_latitude()),
                                "longitude": int(faker.generate_longitude())
                            }
                        ]
                    },
                    "name": faker.generate_name(),
                    "timezone": faker.generate_timezone()
                }
            }
            response = api_instance.send(endpoint_path="site_sites_id", method="PUT", headers=self.headers,
                                         data=data, id=self.site_id, is_valid=True)
            Assertions.assert_status_code(response, 200)
            # 查询site
            response2 = api_instance.send(endpoint_path="site_tree", method="GET", headers=self.headers)
            Assertions.assert_status_code(response2, 200)
            rep2 = json.loads(response2.content)
            data_result = DataUtils.find_item_by_key(data=rep2["sites"], key="id", value=self.site_id)
            Assertions.assert_json(data_result, data, contain={"details"})

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_delete_delete_site_success(self):
        """
        DELETE
        delete site
        请求成功
        """
        try:
            # 新增site
            data = {
                "site": {
                    "name": faker.generate_name(),
                    "timezone": faker.generate_timezone()
                }
            }
            response = api_instance.send(endpoint_path="site_sites", method="POST", headers=self.headers, data=data)
            response.raise_for_status()
            rep = json.loads(response.content)
            site_id = rep["id"]
            # 删除site
            response2 = api_instance.send(endpoint_path="site_sites_id", method="DELETE", id=site_id,
                                          headers=self.headers, is_valid=True)
            Assertions.assert_status_code(response2, 200)
            time.sleep(2)
            # 查询list site
            response3 = api_instance.send(endpoint_path="site_tree", method="GET", headers=self.headers)
            Assertions.assert_status_code(response3, 200)
            rep3 = json.loads(response3.content)
            Assertions.assert_empty(DataUtils.find_item_by_key(data=rep3["sites"], key="id", value=site_id))

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [{}, {'withCameraNum': True}, {'withCameraNum': False}])
    def test_get_site_list_success(self, input_data):
        """
        GET    site tree
        请求成功
        :param input_data: withCameraNum bool
        :return:
        """
        try:
            # 查询site
            response = api_instance.send(endpoint_path="site_tree", method="GET", headers=self.headers,
                                         is_valid=True, params=input_data)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if input_data.get("withCameraNum", False):
                Assertions.assert_contains_key_in_list(rep, "$.sites[*]", "stats")

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

