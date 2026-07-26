# -*- coding: utf-8 -*-
import pytest
import json
import time
from src.utils.assertions import Assertions
from src.utils.data_utils import DataUtils
from src.core.api_exceptions import RequestError
from src.api.client import api_instance
from src.api.ws_client import create_websocket_client, WebSocketRequest


class TestScenarioCamera:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        try:
            cls.siteId = api_instance.dealer_data["sites"]["id"]
            cls.nvrId = api_instance.dealer_data["nvrs"]["id"]
            cls.cameraId = api_instance.dealer_data['cameras'][-1]["id"]
            cls.cameraSN = api_instance.dealer_data['cameras'][-1]["sn"]
        except Exception as e:
            KeyError(f"dealer_data was not fully populated: {str(e)}")
            raise
        print("\nSetting up TestAPI class...")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P0
    @pytest.mark.asyncio
    async def test_camera_addition_and_deletion(self):
        """
        Test camera addition and deletion
        steps:
            1. Get target camera
            2. Delete target camera
            3. Search device
            4. Add camera
        """
        # get target camera
        try:
            get_response = api_instance.send(endpoint_path="camera_cameras_id", method="GET", is_valid=True, id=self.cameraId)
            Assertions.assert_status_code(get_response, 200)
            rep1 = json.loads(get_response.content)
            Assertions.assert_not_empty(rep1["data"])
            self.target_camera_id = rep1["data"]["id"]
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")    

        # camera deletion
        try:   
            del_response = api_instance.send(endpoint_path="camera_cameras_id", method="DELETE", id=self.target_camera_id, is_valid=True)
            Assertions.assert_status_code(del_response, 200)
            time.sleep(2)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        Assertions.assert_raises(RequestError, api_instance.send, endpoint_path="camera_cameras_id", method="GET", is_valid=True, id=self.cameraId)
        
        # device search
        websocket_instance = await create_websocket_client()
        data = {"deviceSearch": {"nvrId": self.nvrId}}
        request_data = WebSocketRequest.create(data)
        search_reply = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        Assertions.assert_not_empty(search_reply["result"]["data"]["deviceSearchReply"]["cameraList"])
        
        self.target_camera = DataUtils.find_item_by_key(
            data=search_reply["result"]["data"]["deviceSearchReply"]["cameraList"], key="sn", value=self.cameraSN, return_parent=False)
        
        # camera addition
        data = {
            "data": [self.target_camera],
            "nvrId": self.nvrId,
            "siteId": self.siteId
        }
        try:
            add_response = api_instance.send(endpoint_path="camera_cameras", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(add_response, 200)
            rep1 = json.loads(add_response.content)
            Assertions.assert_equal(rep1["data"][0]["status"], "success")
            Assertions.assert_equal(rep1["data"][0]["sn"], search_reply["result"]["data"]["deviceSearchReply"]["cameraList"][0]["sn"])
            Assertions.assert_equal(rep1["data"][0]["macAddress"], search_reply["result"]["data"]["deviceSearchReply"]["cameraList"][0]["macAddress"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")   
        





