# -*- coding: utf-8 -*-
import pytest
import asyncio

from src.api.client import api_instance
from src.api.ws_client import create_websocket_client, WebSocketRequest
from src.data.params import WEBSOCKET_PARAMS


class TestWSConnect:

    @pytest.mark.P0
    @pytest.mark.asyncio
    async def test_ws_device_connect(self):
        websocket_instance = await create_websocket_client()
        data = WEBSOCKET_PARAMS["deviceConnect"]
        data["deviceConnect"]["token"] = api_instance.get_token()
        request_data = WebSocketRequest.create(data)
        response = await websocket_instance.send_request(request_data, validate_response=True)
        await websocket_instance.close()
        return response
