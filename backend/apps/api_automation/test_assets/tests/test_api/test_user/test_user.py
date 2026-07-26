# -*- coding: utf-8 -*-
import json
import os

import pytest
from src.api.client import api_instance
from src.utils.assertions import Assertions
from src.data.faker import faker


class TestUser:
    @pytest.mark.skip(reason="请求较少")
    @pytest.mark.parametrize("input_data, expected", [
        (["CUSTOMER_NAME", "CUSTOMER_PASSWORD"], "customer"),
        (["DEALER_NAME", "DEALER_PASSWORD"], "dealer"),
        (["DISTRIBUTORS_NAME", "DISTRIBUTORS_PASSWORD"], "distributor"),
    ])
    def test_post_login_success(self, input_data, expected):
        """
            POST
            测试不同用户登录
            请求成功
        """
        data = {
                "email": os.getenv(input_data[0]),
                "password": os.getenv(input_data[1])
            }
        response = api_instance.send(endpoint_path="auth_login", method="POST", data=data, is_valid=True)
        rep = json.loads(response.content)
        Assertions.assert_status_code(response, 200)
        Assertions.assert_equal(rep["user"]["role"]["name"], expected)
        expect_json = {
            "user": {
                "role": {
                    "name": expected,
                    "desc": expected+" role"
                },
                "email": os.getenv(input_data[0]),
                "status": "enabled",
                "organization": {
                    "type": expected
                },
            },
        }
        Assertions.assert_json(rep, expect_json)

    @pytest.mark.skip(reason="请求较少")
    def test_post_add_dealer_success(self):
        """
            POST
            测试新增dealer账户
            请求成功
        """
        headers = {
            "Authorization": api_instance.distributor_token
        }
        data = {
                "email": faker.generate_email()
        }
        # response = api_instance.distributor_add_dealer(headers=headers)
        response = api_instance.send(endpoint_path="user_dealers", method="POST", data=data, headers=headers,
                                     is_valid=True)
        rep = json.loads(response.content)
        Assertions.assert_status_code(response, 200)
        Assertions.assert_equal(rep, {})
        api_instance.login("CUSTOMER")



