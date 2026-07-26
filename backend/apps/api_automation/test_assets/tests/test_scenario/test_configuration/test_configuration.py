# -*- coding: utf-8 -*-
import json
import pytest
from datetime import datetime
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.utils.data_utils import DataUtils

class TestConfiguration:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    def test_virtual_guard_configuration(self):
        """
        测试 virtual guard 配置
        steps:
        1. generate virtual guard instruction prompt
        2. create virtual guard template-1 with the prompt
        3. get virtual guard instruction template list
        4. update voice and shcedule for virtual guard template-1
        5. delete virtual guard template-1

        """
        # generate virtual guard instruction prompt
        user_data_for_prompt = {
            "workflow": {
                "trigger": "people is holding a gun",
                "intention": "ask to put it down immediately",
                "tone": "Urgent",
                "id": str(datetime.now().timestamp() * 1000)
            }
        }
        try:
            response_1 = api_instance.send(endpoint_path="openai_gen_vg_instruction_prompt", method="POST", data=user_data_for_prompt, is_valid=True)
            rep = json.loads(response_1.content)
            Assertions.assert_status_code(response_1, 200)
            custom_prompt = rep.get("customPrompt", "")
            Assertions.assert_not_empty(custom_prompt)
            user_data_for_prompt["workflow"]["customPrompt"] = custom_prompt
        except AssertionError:
            raise
        except Exception as e:
            raise RequestError(f"Request Error while gen vg instruction prompt: {str(e)}")
        print(f"lijun user_data_for_prompt: {user_data_for_prompt}")
        # create virtual guard template-1
        user_data_for_instruction = {
            "data": {
                "voice": "alloy",
                "workflows": [user_data_for_prompt["workflow"]],
                "schedule": {
                    "allYear": True,
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
            }
        }
        
        try:
            response_2 = api_instance.send(endpoint_path="virtual_guard_instruction", method="POST", data=user_data_for_instruction, is_valid=True)
            Assertions.assert_status_code(response_2, 200)
        except Exception as e:
            raise RequestError(f"Error while create virtual guard template-1: {str(e)}")

        # check virtual guard template-1 from template list
        param = {"page.limit": 10}
        try:
            response_3 = api_instance.send(endpoint_path="virtual_guard_instruction_list", method="GET", params=param, is_valid=True)
            Assertions.assert_status_code(response_3, 200)
            rep = json.loads(response_3.content)
            Assertions.assert_not_empty(rep["data"])
            target_instruction = DataUtils.find_item_by_key(data=rep["data"], key="name", value="test_virtual_guard_template_1", return_parent=True)

            target_instruction_id = target_instruction.get("id", "")
            target_instruction_voice = target_instruction.get("voice", "")
            target_instruction_schedule = target_instruction.get("schedule", {})
            target_instruction_workflows = target_instruction.get("workflows", [])

            Assertions.assert_not_empty(target_instruction_workflows)
            Assertions.assert_equal(target_instruction_workflows[0].get("trigger"), user_data_for_prompt["workflow"]["trigger"])
            Assertions.assert_equal(target_instruction_workflows[0].get("intention"), user_data_for_prompt["workflow"]["intention"])
            Assertions.assert_equal(target_instruction_workflows[0].get("tone"), user_data_for_prompt["workflow"]["tone"])
            Assertions.assert_equal(target_instruction_voice, user_data_for_instruction["data"]["voice"])
            Assertions.assert_equal(target_instruction_schedule, user_data_for_instruction["data"]["schedule"])
        except AssertionError as e:
            response_del = api_instance.send(endpoint_path="virtual_guard_instruction_id", method="DELETE", id=target_instruction_id, is_valid=True)
            Assertions.assert_status_code(response_del, 200)
            raise AssertionError(f"Assertion Failed: {str(e)}")
        except Exception as e:
            raise RequestError(f"Request Error while get virtual guard instruction template list: {str(e)}")

        # update virtual guard template-1
        schedule = {
            "allYear": False,
            "allDay": False,
            "timeRanges": [
                {
                "startedAt": 25200,
                "endedAt": 68400
                }
            ],
            "weekdays": [
                "tuesday",
                "thursday",
                "saturday",
                "sunday"
            ]
        }
        user_data_for_instruction["data"]["voice"] = "nova"
        user_data_for_instruction["data"]["schedule"] = schedule

        try:
            response_4 = api_instance.send(endpoint_path="virtual_guard_instruction_id", method="PUT", id=target_instruction_id, data=user_data_for_instruction, is_valid=True)
            Assertions.assert_status_code(response_4, 200)
        except Exception as e:
            raise RequestError(f"Error while update virtual guard template-1: {str(e)}")

        # check virtual guard template-1 is updated
        try:
            response_5 = api_instance.send(endpoint_path="virtual_guard_instruction_id", method="GET", id=target_instruction_id, is_valid=True)
            Assertions.assert_status_code(response_5, 200)
            rep = json.loads(response_5.content)
            Assertions.assert_equal(rep["data"]["voice"], "nova")
            Assertions.assert_equal(rep["data"]["schedule"], schedule)
        except AssertionError as e:
            raise AssertionError(f"Assertion Failed: {str(e)}")
        except Exception as e:
            raise RequestError(f"Error while get virtual guard template-1 by id {target_instruction_id}: {str(e)}")

        # delete virtual guard template-1
        try:
            response_6 = api_instance.send(endpoint_path="virtual_guard_instruction_id", method="DELETE", id=target_instruction_id, is_valid=True)
            Assertions.assert_status_code(response_6, 200)
        except Exception as e:
            raise RequestError(f"Error while delete virtual guard template-1 by id {target_instruction_id}: {str(e)}")

        # check virtual guard template-1 is deleted from template list
        param = {"page.limit": 10}
        try:
            response_7 = api_instance.send(endpoint_path="virtual_guard_instruction_list", method="GET", params=param, is_valid=True)
            rep = json.loads(response_7.content)
            Assertions.assert_status_code(response_7, 200)
            res = DataUtils.find_item_by_key(data=rep["data"], key="name", value="test_virtual_guard_template_1")
            Assertions.assert_equal(res, None)
        except AssertionError as e:
            raise AssertionError(f"Assertion Failed: {str(e)}")
        except Exception as e:
            raise RequestError(f"Error while get virtual guard instruction template list: {str(e)}")