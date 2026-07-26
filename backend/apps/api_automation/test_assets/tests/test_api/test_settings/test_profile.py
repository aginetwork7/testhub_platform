# -*- coding: utf-8 -*-
import json
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker
from src.utils.argon2_password_encryptor import PasswordEncryptor

class TestProfile:
    
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        cls.username = api_instance.current_auth_info.username
        cls.password = api_instance.current_auth_info.password
        cls.encryptor = PasswordEncryptor()
        
    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")
    
    @pytest.mark.P0
    def test_get_get_user_profile_success(self):
        """
        GET user_profile
        success
        :param
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="user_profile", method="GET", is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_not_empty(rep)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_patch_update_user_profile_success(self):
        """
        PATCH user_profile
        success
        :param
        :return:
        """
        test_data = {
            "firstName": faker.generate_name(),
            "lastName": faker.generate_name(),
            "orgTimezone": faker.generate_timezone(),
            "timezone": faker.generate_timezone()
        }
        try:
            response_pat = api_instance.send(endpoint_path="user_profile", method="PATCH", is_valid=True, data=test_data)
            Assertions.assert_status_code(response_pat, 200)
            response_get = api_instance.send(endpoint_path="user_profile", method="GET", is_valid=True)
            Assertions.assert_status_code(response_get, 200)
            rep = json.loads(response_get.content)
            Assertions.assert_equal(rep["firstName"], test_data["firstName"])
            Assertions.assert_equal(rep["lastName"], test_data["lastName"])
            Assertions.assert_equal(rep["orgTimezone"], test_data["orgTimezone"])
            Assertions.assert_equal(rep["timezone"], test_data["timezone"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        finally:
            restore_data = {
                "firstName": "Test Customer",
                "lastName": "Account",
                "orgTimezone": 'Asia/Shanghai',
                "timezone": 'Asia/Shanghai'
            }
            response = api_instance.send(endpoint_path="user_profile", method="PATCH", is_valid=True, data=restore_data)
            Assertions.assert_status_code(response, 200)
            
    @pytest.mark.P0
    def test_post_change_password_success(self):
        """
        POST auth_change_password
        success
        :param
        :return:
        """
        newPassword = self.encryptor.encrypt_stage('test123', self.username, 'network')
        oldPassword = self.encryptor.encrypt_stage(self.password, self.username, 'network')
        data = {
            "newPassword": newPassword,
            "oldPassword": oldPassword,
            "oldPasswordV2": oldPassword
        }
        try:
            response = api_instance.send(endpoint_path="auth_change_password", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            data = {
                    "email": self.username,
                    "password": newPassword,
                    "password_v2": newPassword
                }
            response = api_instance.send(endpoint_path="auth_login", method="POST", data=data, is_valid=True)
            Assertions.assert_status_code(response, 200)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")  

        finally:
            data_restore = {
                "newPassword": oldPassword,
                "oldPassword": newPassword,
                "oldPasswordV2": newPassword
            }
            response = api_instance.send(endpoint_path="auth_change_password", method="POST", is_valid=True, data=data_restore)
            Assertions.assert_status_code(response, 200)