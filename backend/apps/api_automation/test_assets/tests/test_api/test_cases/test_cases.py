# -*- coding: utf-8 -*-
import json
import pytest
from pathlib import Path
from time import sleep
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.core.logger import logger
from src.core.config import config
from src.data.faker import faker

class TestCases:
    _data_cache = {}
    enable_local_cache = config.get("api.database.enable_local_cache", False)
    _cache_file = Path(config.get("test.data.db_cache_file", "data/database/cache.yaml"))

    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        logger.info("\nPreparing...")
        #TODO 1. prepare alert and case data
        case_response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True)
        Assertions.assert_status_code(case_response, 200)
        rep_case = json.loads(case_response.content)
        Assertions.assert_not_empty(rep_case["data"])
        cls.case_0_metadata = rep_case["data"][0]
        cls.caseId = rep_case["data"][0]["id"]
        cls.displayId = rep_case["data"][0]["displayId"]
        cls.status = rep_case["data"][0]["status"]
        cls.siteId = rep_case["data"][0]["alerts"][0]["siteId"]
        cls.cameraId = rep_case["data"][0]["alerts"][0]["cameraId"]
        cls.cameraName = rep_case["data"][0]["alerts"][0]["camera"]["name"]
        #TODO 2. for inspector alert, createdAt = endedAt, so case test_delete_archive_from_case_success will be failed, need to create by api
        cls.createdAt = int(rep_case["data"][0]["alerts"][0]["createdAt"])
        cls.startAt = int(rep_case["data"][0]["alerts"][0]["startedAt"])
        cls.endedAt = int(rep_case["data"][0]["alerts"][0]["endedAt"])
        param = {"statuses": "todo"}
        alert_response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
        Assertions.assert_status_code(alert_response, 200)
        rep_alert = json.loads(alert_response.content)
        cls.alertId = rep_alert["data"][0]["id"]
      
        logger.info("\nPrepared...")

        
    @pytest.mark.P0
    def test_get_list_cases_success(self):
        """
        GET    
        list cases
        Success
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["paging"]["limit"], 20)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0      
    def test_get_get_case_success(self):
        """
        GET    
        get one case with ID
        Success
        :param
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            Assertions.assert_equal(rep["data"]["id"], self.caseId)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_cases_success_by_displayid(self):
        """
        GET    
        search cases by case id
        Success
        :param id
        :return:
        """
        param = {"displayId": self.displayId}
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["data"][0]["displayId"], self.displayId)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_cases_success_by_status(self):
        """
        GET    
        search cases by case status
        Success
        :param status
        :return:
        """
        param = {"statuses": "investigate"}
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_equal(rep["data"][0]["status"], param["statuses"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_cases_success_by_tag(self):
        """
        GET    
        search cases by case tag
        Success
        :param tags
        :return:
        """
        param = {"tags": faker.generate_alert_tag()}
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_equal(param["tags"], rep["data"][0]["tag"]["name"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
         
    @pytest.mark.P0
    def test_get_search_cases_success_by_date(self):
        """
        GET    
        search alerts by alert date
        Success
        :param
        :return:
        """
        timestamps = faker.generate_timestamps_in_period(unit="day", precision="ms")
        param = {
            "startedAt": timestamps[0],
            "endedAt": timestamps[1]
        }
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_true(param["startedAt"] <= int(rep["data"][0]["createdAt"]) <= param["endedAt"]) 
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")       

    @pytest.mark.P0
    def test_get_search_cases_success_by_site(self):
        """
        GET    
        search alerts by site and camera
        Success
        :param input_data:
        :return:
        """
        param = {"siteIds": self.siteId}
        try:
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_true(rep["data"][0]["alerts"][0]["siteId"] == param["siteIds"])
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_cases_success_by_star(self):
        """
        GET    
        search alerts by star
        Success
        :param input_data:
        :return:
        """
        param = {
            "star": True,
            "paging.limit": 20
        }
        try:
            param = {"star": True}
            # set case star
            response = api_instance.send(endpoint_path="case_cases_id_star", method="PUT", is_valid=True, data=param, id=self.caseId)
            Assertions.assert_status_code(response, 200)

            # search case star
            response = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_true(rep["data"][0]["star"] == True)
                Assertions.assert_equal(rep["data"][0]["id"], self.caseId)
            else:
                pytest.fail("No starred case set success or search star case failed.")
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")     

    @pytest.mark.P0
    def test_put_cases_star_success(self):
        """
        PUT    
        star case
        Success
        :param input_data:
        :return:
        """
        try:
            param = {"star": True}
            # set case star
            response = api_instance.send(endpoint_path="case_cases_id_star", method="PUT", is_valid=True, data=param, id=self.caseId)
            Assertions.assert_status_code(response, 200)

            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["data"]["star"], True)

            # cancle set case star
            param = {"star": False}           
            response = api_instance.send(endpoint_path="case_cases_id_star", method="PUT", is_valid=True, data=param, id=self.caseId)
            Assertions.assert_status_code(response, 200)

            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["data"]["star"], False)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_dispatch_cases_to_guard_success(self):
        """
        POST    
        dispatch case to guard
        Success
        :param input_data:
        :return:
        """
        # 获取当前site的guard id
        param = {"siteId": self.siteId}
        guard_response = api_instance.send(endpoint_path="user_guards", method="GET", is_valid=True, params=param)
        Assertions.assert_status_code(guard_response, 200)
        rep_guard = json.loads(guard_response.content)

        if len(rep_guard["data"]) == 0:
            pytest.skip("No guard to dispatch,please manual add guard to site.")       
        else:
            self.guardId = rep_guard["data"][0]["id"]

            input_data = {
                "guardCompny": {
                    "name": ""
                },
                "guardIds": [self.guardId]
            }
            try:
                response = api_instance.send(endpoint_path="case_cases_caseId_dispatch", method="POST", is_valid=True, data=input_data, caseId=self.caseId)
                Assertions.assert_status_code(response, 200)

                response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
                Assertions.assert_status_code(response, 200)
                rep = json.loads(response.content)
                Assertions.assert_not_empty(rep["data"])
                Assertions.assert_equal(rep["data"]["guards"][0]["id"], self.guardId)
            except Exception as e:
                raise RequestError(f"An unexpected error occurred: {str(e)}") 

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
            {"status": "call_pd"},
            {"status": "resolved"},
            {"status": "closed"},
            {
                "status": "investigate",
                "tag": {
                    "desc": "",
                    "name": faker.generate_alert_tag()
                }
            }
        ])    
    def test_post_change_case_status_success(self, input_data):
        """
        POST    
        change case status
        Success
        :param input_data:status and tag
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="case_cases_id_change_status", method="POST", is_valid=True, data=input_data, id=self.caseId)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"Error occurred during change case status: {str(e)}")
        try:
            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            Assertions.assert_equal(rep["data"]["status"], input_data["status"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0  
    @pytest.mark.parametrize("input_data", [
            {
                "status": "investigate"
            }
        ])    
    def test_get_case_status_count_success(self, input_data):
        """
        GET    
        status count
        Success
        :param input_data:status
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="case_cases_status_count", method="GET", is_valid=True, params=input_data)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0    
    def test_post_add_case_note_success(self):
        """
        POST   
        add case note
        Success
        :param   note
        :return:
        """
        data = {"note": "This is a test case note!"}
        try:
            # add an case note
            response_add = api_instance.send(endpoint_path="case_cases_caseId_notes", method="POST", is_valid=True, data=data, caseId=self.caseId)
            Assertions.assert_status_code(response_add, 200)
            rep_add = json.loads(response_add.content)
            Assertions.assert_not_empty(rep_add["noteId"])
            # get case note
            response_get = api_instance.send(endpoint_path="case_cases_caseId_notes", method="GET", is_valid=True, caseId=self.caseId)
            Assertions.assert_status_code(response_get, 200)
            rep_get = json.loads(response_get.content)
            Assertions.assert_not_empty(rep_get["notes"])
            Assertions.assert_equal(rep_get["notes"][-1]["note"], data["note"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_post_merge_alert_into_case_success(self):
        """
        POST   
        merge alert into case
        Success
        :param   alertId, caseId
        :return:
        """
        data = {
            "alertId": self.alertId,
            "caseId": self.caseId
        }
        try:
            # merge alert into case
            response_add = api_instance.send(endpoint_path="case_cases_merge_into", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response_add, 200)
            # sleep 2s to wait merge complete
            sleep(2)
            # get alert from case
            response_get = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response_get, 200)
            rep_get = json.loads(response_get.content)
            Assertions.assert_not_empty(rep_get["data"]["alerts"])
            Assertions.assert_equal(rep_get["data"]["alerts"][-1]["id"], self.alertId)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_merge_case_into_case_success(self):
        """
        POST   
        merge case into case
        Success
        :param   caseId, mergeCaseId
        :return:
        """
        
        try:
            # get alert from case
            response_get = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response_get, 200)
            rep_get = json.loads(response_get.content)
            Assertions.assert_not_empty(rep_get["data"]["alerts"])
            alert_id = rep_get["data"]["alerts"][0]["id"]

            # get alert mergeable case id
            param = {
                "alertId": alert_id,
                "forCase": True,
                "withCustomer": False
            }
            response = api_instance.send(endpoint_path="case_cases_mergeable", method="GET", is_valid=True, params = param)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            if len(rep["data"]) == 0:
                pytest.skip("No mergeable case found")
            else:
                merge_case_id = rep["data"][0]["id"]
        
                data = {
                    "destinationCaseId": merge_case_id,
                    "sourceCaseId": self.caseId        
                }       
                # merge case into case
                response_add = api_instance.send(endpoint_path="case_cases_merge_case_into", method="POST", is_valid=True, data=data)
                Assertions.assert_status_code(response_add, 200)      
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_archive_case_success(self):
        """
        POST   
        archive case
        Success
        :param   cameraId, cameraName, endAt, startAt
        :return:
        """
        data = {
            "cameraId": self.cameraId,
            "cameraName": self.cameraName,
            "endAt": int(self.endedAt / 1000) + 1,
            "startAt": int(self.startAt / 1000),
            "streamId": 0
        }
        try:
            response = api_instance.send(endpoint_path="case_cases_caseId_archive", method="POST", is_valid=True, caseId=self.caseId, data=data)
            Assertions.assert_status_code(response, 200)
            # 验证archive video成功
            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"]["archives"])  
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")   
        
    @pytest.mark.P0
    def test_delete_archive_from_case_success(self):
        """
        POST   
        delete archive from case
        Success
        :param   alertId, caseId
        :return:
        """
        data = {
            "cameraId": self.cameraId,
            "cameraName": self.cameraName,
            "endAt": int(self.endedAt / 1000) + 1,
            "startAt": int(self.startAt / 1000)
        }
        try:
            response = api_instance.send(endpoint_path="case_cases_caseId_archive", method="POST", is_valid=True, caseId=self.caseId, data=data)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        try:
            # get archive video
            response = api_instance.send(endpoint_path="case_cases_id", method="GET", is_valid=True, id=self.caseId)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            self.archiveId = rep["data"]["archives"][-1]["id"]
            # delete archive video with id
            response_add = api_instance.send(endpoint_path="case_cases_caseId_archive_archiveId", method="DELETE", is_valid=True, caseId=self.caseId, archiveId=self.archiveId)
            Assertions.assert_status_code(response_add, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_post_share_case_success(self):
        """
        GET    
        share case
        Success
        :param
        :return:
        """
        data = {
            "data":{
                "caseId": self.caseId,
                "contacts": {
                    "manualEmailNotifier": {"emails": ["ms_dealer@outlook.com"]}
                }
            }
        }
        try:
            response = api_instance.send(endpoint_path="sharing_shares_public_case", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            Assertions.assert_equal(rep["data"]["caseId"], self.caseId)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")      

    @pytest.mark.P0
    def test_post_case_medias_success(self):
        """
        POST   
        upload case medias
        Success
        :param
        :return:
        """
        s3_key, yolo_data = api_instance.prepare_data_for_record("human")
        data = {
            "medias": [
                {
                    "key": s3_key,
                    "type": "image"
                }
            ]
        }
        try:
            # post media image
            response = api_instance.send(endpoint_path="case_cases_caseId_medias", method="POST", is_valid=True, caseId=self.caseId, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["mediaIds"])
            Assertions.assert_equal(rep["caseId"], self.caseId)
            media_id = rep["mediaIds"][0]

            # get media image
            response = api_instance.send(endpoint_path="case_cases_caseId_medias", method="GET", is_valid=True, caseId=self.caseId, params={})
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["medias"][-1]["id"], media_id)
            Assertions.assert_startswith(rep["medias"][-1]["s3File"]["key"], "/org")

            # delete media
            response = api_instance.send(endpoint_path="case_cases_caseId_medias_mediaId", method="DELETE", is_valid=True, caseId=self.caseId, mediaId=media_id)
            Assertions.assert_status_code(response, 200)                  
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")