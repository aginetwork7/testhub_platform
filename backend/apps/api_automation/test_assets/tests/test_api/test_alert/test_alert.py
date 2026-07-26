# -*- coding: utf-8 -*-
import json
import time
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.core.logger import logger
from src.core.config import config
from src.data.faker import faker
from src.utils.data_utils import DataUtils
from pathlib import Path

class TestAlertCustomer:
    _data_cache = {}
    enable_local_cache = config.get("api.database.enable_local_cache", False)
    _cache_file = Path(config.get("test.data.db_cache_file", "data/database/cache.yaml"))

    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        logger.info("\nPreparing...")
        if cls.enable_local_cache:
            # 使用 api_instance 的缓存方法
            cls._data_cache = api_instance._load_cache(cls._cache_file)
        response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True)
        Assertions.assert_status_code(response, 200)
        rep_alert = json.loads(response.content)
        Assertions.assert_not_empty(rep_alert["data"])
        cls.alert_0_metadata = rep_alert["data"][0]
        cls.site_id = rep_alert["data"][0]["siteId"]
        cls.camera_id = rep_alert["data"][0]["cameraId"]
        cls.alert_id_0 = rep_alert["data"][0]["id"]
        if "assetTrackingList" in rep_alert["data"][0] and len(rep_alert["data"][0]["assetTrackingList"]) > 0:
            cls.database_id_0 = rep_alert["data"][0]["assetTrackingList"][0]["id"]
        else:
            cls.database_id_0 = None
        cls.start_time = rep_alert["data"][0]["startedAt"]
        cls.end_time = rep_alert["data"][0]["endedAt"]
        cls.page_last = rep_alert["paging"].get("last", '')
        cls.hasNext = rep_alert["paging"].get("hasNext", False)
        
        timestamps = faker.generate_timestamps_in_period(unit="day", precision="s")
        cls.today_timestamp_start = timestamps[0]
        cls.today_timestamp_end = timestamps[1]

        logger.info("\nPrepared...")
        
    @pytest.mark.P0
    def test_get_list_alerts_success(self):
        """
        GET    
        list alerts
        Success
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep["paging"]["limit"], 20)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_load_more_alerts_success(self):
        """
        GET    
        load more alerts
        Success
        :param input_data:
        :return:
        """
        try:
            if not self.hasNext:
                logger.info("This case is skipped because hasNext is False.")
                pass
            param = {
                "paging.limit": 10,
                "paging.last": self.page_last
            }
            if param.get("paging.last", "False"):
                response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params = param)
                rep = json.loads(response.content)
                Assertions.assert_status_code(response, 200)
                Assertions.assert_not_empty(rep["data"])
                Assertions.assert_not_equal(rep["paging"]["last"], param["paging.last"])
                Assertions.assert_equal(rep["paging"]["limit"], param["paging.limit"])
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}") 

    @pytest.mark.P0
    def test_get_search_alerts_success_by_critical(self):
        """
        GET    
        search alerts by alert critical
        Success
        :param input_data:
        :return:
        """
        param = {"isCritical": "true"}
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)

            if len(rep["data"]) > 0:
                Assertions.assert_equal(rep["data"][0]["warnLevel"], "level_critical")
            else:
                pytest.skip("No critical alert found.")
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_alerts_success_by_vg(self):
        """
        GET    
        search alerts by alert virtualguard
        Success
        :param input_data:
        :return:
        """
        param = {"hasVirtualGuard": "true"}
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)

            if len(rep["data"]) > 0:
                Assertions.assert_not_equal(rep["data"][0]["virtualGuard"], "null")
            else:
                pytest.skip("No virtualguard alert found.")
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("event_type", ["person", "human_sitting", "vehicle", "database"])
    def test_get_search_alerts_success_by_type(self, event_type):
        """
        GET    
        search alerts by alert type
        Success
        :param input_data:
        :return:
        """
        param = {"eventTypes": event_type}
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_in(param["eventTypes"], rep["data"][0]["eventTypes"])
                if event_type == "database":
                    Assertions.assert_not_equal(0, len(rep["data"][0]["assetTrackingList"]))
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_alerts_success_by_personCoatColors(self):
        """
        GET    
        search alerts by person coat colors
        Success
        :param input_data:
        :return:
        """

        try:
            param = {"eventTypes": "person", "personCoatColors": "white"}
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_in(param["personCoatColors"], rep["data"][0]["attrs"]["persons"][0]["coatColor"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
         
    @pytest.mark.P0
    def test_get_search_alerts_success_by_status(self):
        """
        GET    
        search alerts by alert alert status
        Success
        :param input_data:
        :return:
        """
        param = {"statuses": "investigate"}
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_equal(rep["data"][0]["status"], param["statuses"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_search_alerts_success_by_timerange(self):
        """
        GET    
        search alerts by alert timerange
        Success
        :param input_data:
        :return:
        """
        param = {
            "startedAt": self.start_time,
            "endedAt": self.end_time
        }
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_true(param["startedAt"] <= rep["data"][0]["createdAt"] <= param["endedAt"]) 
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")       

    @pytest.mark.P0
    def test_get_search_alerts_success_by_cameras(self):
        """
        GET    
        search alerts by site and camera
        Success
        :param input_data:
        :return:
        """
        param = {
            "siteIds": self.site_id,
            "cameraIds": self.camera_id
        }
        try:
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            if len(rep["data"]) > 0:
                Assertions.assert_true(rep["data"][0]["siteId"] == param["siteIds"] and rep["data"][0]["cameraId"] == param["cameraIds"])
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")   

    @pytest.mark.P0
    def test_get_search_alerts_success_by_database_record(self):
        """
        GET    
        search alerts by database and record
        Success
        :param input_data:
        :return:
        """
        try:
            # search by eventype:database,确保拿到有database和record关联的alert
            param = {"eventTypes": "database"}
            response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            
            if len(rep["data"]) > 0:   
                Assertions.assert_in(param["eventTypes"], rep["data"][0]["eventTypes"])

                tracking_Group_Id = rep["data"][0]["assetTrackingList"][0]["id"]
                record_Id = rep["data"][0]["assetTrackingList"][0]["recordId"]
                param1 = {"trackingGroupId": tracking_Group_Id}
                param2 = {"trackingGroupId": tracking_Group_Id, "trackingId": record_Id}   

                # search by database trackingGroupId
                response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param1)
                rep = json.loads(response.content)
                Assertions.assert_status_code(response, 200)
                # 因顺序的不确定性，修改断言为检查包含
                # Assertions.assert_equal(rep["data"][0]["assetTrackingList"][0]["id"], tracking_Group_Id)
                Assertions.assert_has_value(rep["data"][0]["assetTrackingList"], "[*].id", tracking_Group_Id)

                # search by database trackingGroupId & record recordId
                response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params=param2)
                rep = json.loads(response.content)
                Assertions.assert_status_code(response, 200)
                # Assertions.assert_equal(rep["data"][0]["assetTrackingList"][0]["recordId"], record_Id)
                Assertions.assert_has_value(rep["data"][0]["assetTrackingList"], "[*].recordId", record_Id)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
    
    @pytest.mark.P0      
    def test_get_get_alert_success(self):
        """
        GET    
        get one alert with ID
        Success
        :param alert_id:id
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="alert_alerts_id", method="GET", is_valid=True, id=self.alert_id_0)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
            {"status": "todo"},
            {"status": "closed"},
            {"status": "false_alarm"},
            {
                "status": "investigate",
                "tag": {
                    "desc": "",
                    "name": faker.generate_alert_tag()
                }
            }
        ])    
    def test_post_change_alert_status_success(self, input_data):
        """
        POST    
        change alert status
        Success
        :param input_data:status and tag
        :return:
        """
        if self.alert_0_metadata.get("status", "todo") == "investigate":
            logger.info("This case is skipped because alert alreay in investigate.")
            return
        try:
            response = api_instance.send(endpoint_path="alert_alerts_id_change_status", method="POST", is_valid=True, data=input_data, id=self.alert_id_0)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"Error occurred during change alert status: {str(e)}")
        try:
            response = api_instance.send(endpoint_path="alert_alerts_id", method="GET", is_valid=True, id=self.alert_id_0)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            Assertions.assert_equal(rep["data"]["status"], input_data["status"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0  
    @pytest.mark.parametrize("input_data", [
            {
                "status": "todo"
            }
        ])    
    def test_get_status_count_success(self, input_data):
        """
        GET    
        status count
        Success
        :param input_data:status
        :return:
        """
        try:
            response = api_instance.send(endpoint_path="alert_alerts_status_count", method="GET", is_valid=True, params=input_data)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_merge_alert_to_case_success(self):
        """
        POST
        merge alert to case
        Success
        :param
        :return:
        """
        # 查询当前site todo的alert列表
        param = {
            "searchFlag" : 0,
            "isCritical": False,
            "siteIds": self.site_id,
            "statuses": "todo",
            "paging.limit": 10
        }
        response = api_instance.send(endpoint_path="alert_alerts", method="GET", is_valid=True, params = param)
        Assertions.assert_status_code(response, 200)

        rep = json.loads(response.content)
        # 获取并查看alert数目，需要2个alert才能merge
        if len(rep["data"]) < 2:
            pytest.skip("Not enough 'todo' alerts available to run merge test.")
        else:
            # 拿到两个alert的id，alert_case_id处理为case，alert_merge_id用来 merge到case
            alert_case_id = rep["data"][0]["id"]
            alert_merge_id = rep["data"][1]["id"]

            # alert_case_id处理为case
            input_data = {
                "status": "investigate",
                "tag": {
                    "desc":"",
                    "name":"illegal_dumping"
                }
            }
            response2 = api_instance.send(endpoint_path="alert_alerts_id_change_status", method="POST", is_valid=True, data=input_data, id=alert_case_id)
            # 校验alert处理为case成功
            Assertions.assert_status_code(response2, 200)

            # 查看并拿到这个case的case id和displayId
            param = {
                "withLocation": True,
                "withAlertNote": True,
                "withCustomer":False
            }
            response3 = api_instance.send(endpoint_path="case_cases_alert_id", method="GET", is_valid=True, id=alert_case_id, params=param)
            rep3 = json.loads(response3.content)
            case_id = rep3["data"]["id"]
            case_display_id = rep3["data"]["displayId"]
            # time.sleep(5)
            try:
                # 验证：case_id在 alert_merge_id可merge的case列表中,且按照时间顺序排在第一位
                param = {
                    "alertId": alert_merge_id,
                    "withCustomer": False,
                    "forCase": False
                }
                response6 = api_instance.send(endpoint_path="case_cases_mergeable", method="GET", is_valid=True, params=param)
                rep6 = json.loads(response6.content)
                Assertions.assert_not_empty(rep6["data"])
         
                # 将alert_merge_id 这个alert ，merge到case_id
                datas = {
                    "alertId": alert_merge_id,
                    "caseId": case_id
                }
                response4 = api_instance.send(endpoint_path="case_cases_merge_into", method="POST", is_valid=True, data=datas)

                # 验证1: 验证merge接口返回成功
                Assertions.assert_status_code(response4, 200)
                # 查看case详情
                param = {
                    "withLocation": True,
                    "withAlertNote": True,
                    "withCustomer":False
                }
                rep5 = {}
                for _ in range(10):
                    response5 = api_instance.send(endpoint_path="case_cases", method="GET", is_valid=True, displayId=case_display_id, params=param)
                    rep5 = json.loads(response5.content)
                    alert_ids = [alert.get("id") for alert in rep5["data"][0].get("alerts", [])]
                    if alert_merge_id in alert_ids:
                        break
                    time.sleep(1)
                # 验证2:验证merge的alert id在case查询的结果中
                Assertions.assert_has_value(rep5["data"][0]["alerts"], "[*].id", alert_merge_id)
                # 验证3:验证case_display_id和case_id正确
                Assertions.assert_equal(rep5["data"][0]["displayId"], case_display_id)
                Assertions.assert_equal(rep5["data"][0]["id"], case_id)
            except Exception as e:
                raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_get_site_pd_station_success(self):
        """
        GET
        site pd station
        Success
        :param
        :return:
        """
        param = {
            "withManager" : True,
            "with_geolocation": True,
            "withCustomer": False
        }
        try:
            response = api_instance.send(endpoint_path="site_sites_normal_id", method="GET", is_valid=True, id=self.site_id, params=param)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep["data"]["id"], self.site_id)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")            

    @pytest.mark.P0    
    def test_post_add_alert_note_success(self):
        """
        POST   
        add alert note
        Success
        :param input_data:status
        :return:
        """
        data = {
            "alertId": self.alert_id_0,
            "note": "This is a test alert note!"
        }
        try:
            # add an alert note
            response_add = api_instance.send(endpoint_path="alert_notes", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response_add, 200)
            rep_add = json.loads(response_add.content)
            Assertions.assert_not_empty(rep_add["noteId"])
            # get alert note
            alert_param = {
                "alertId": self.alert_id_0
            }
            response_get = api_instance.send(endpoint_path="alert_notes", method="GET", is_valid=True, params=alert_param)
            Assertions.assert_status_code(response_get, 200)
            rep_get = json.loads(response_get.content)
            Assertions.assert_not_empty(rep_get["notes"])
            Assertions.assert_equal(rep_get["notes"][-1]["note"], data["note"])
            # delete alert note
            response_del = api_instance.send(endpoint_path="alert_alerts_alertId_notes_noteId", method="DELETE", is_valid=True, alertId=self.alert_id_0, noteId=rep_add["noteId"])
            Assertions.assert_status_code(response_del, 200)
            response_get = api_instance.send(endpoint_path="alert_notes", method="GET", is_valid=True, params=alert_param)
            Assertions.assert_status_code(response_get, 200)
            rep_get = json.loads(response_get.content)         
            for i in range(len(rep_get["notes"])):
                if rep_get["notes"][i]["noteId"] == rep_add["noteId"]:
                    assert False
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_get_alert_playback_success(self):
        """
        GET    
        view alert playback
        Success
        :param
        :return:
        """
        param = {
            "startedAt": self.start_time,
            "endedAt": self.end_time,
            "cameraIds": self.camera_id
        }
        try:
            response = api_instance.send(endpoint_path="alert_alerts_playback", method="GET", is_valid=True, params=param)
            rep_get = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_equal(rep_get['data'][0]['camera']['id'], self.camera_id)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_post_share_alert_success(self):
        """
        GET    
        share alert
        Success
        :param
        :return:
        """
        data = {
            "data":{
                "alertId": self.alert_id_0,
                "contacts": {
                    "manualEmailNotifier": {"emails": ["ms_dealer@outlook.com"]}
                }
            }
        }
        try:
            response = api_instance.send(endpoint_path="sharing_shares_public_alert", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["data"])
            Assertions.assert_equal(rep["data"]["alertId"], self.alert_id_0)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_alert_link_database_success(self):
        """
        POST  
        alert relate record
        Success
        :param
        :return:
        """
        param = {
            "name": ""
        }         
        response = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=param)
        rep = json.loads(response.content)

        # 先获取到可用的database
        if len(rep["databases"]) > 0:
            database_id = rep["databases"][0]["id"]
            # 根据databaseid查询到可用的human 类型的record_id，因为alert仅可以绑定human类型的record
            param = {
                "type": "human",
                "search": "",
                "trackingGroupId": database_id
            }
            response1 = api_instance.send(endpoint_path="asset_tracking_records", method="GET", is_valid=True, params=param)
            rep2 = json.loads(response1.content)
            if len(rep2["records"]) > 0:
                # 获取要绑定的recordid
                record_id = rep2["records"][0]["id"]
            else:
                logger.warning("No records found, skipping test")
                pytest.skip("No records found")
        else:
            logger.warning("No database found, skipping test")
            pytest.skip("No database found")
        
        try:
            # 记录下当前alert的alertid
            target_alert_id = self.alert_id_0
            # 记录下当前alert所属的siteid
            target_site_id = self.site_id

            rec_data = {
                "alertId": target_alert_id,
                "isRelate": True,
                "recordId": record_id
            }
            # 绑定recordid到alert
            response2 = api_instance.send(endpoint_path="asset_tracking_alert_relate", method="POST", is_valid=True, data=rec_data)
            Assertions.assert_status_code(response2, 200)

            param1 = {
                "start": self.today_timestamp_start,
                "end": self.today_timestamp_end
            }

            # 查看database下对应的record 详情
            response3 = api_instance.send(endpoint_path="asset_tracking_record_detail_id",
                                          method="GET", is_valid=True, id=record_id, params=param1)
            rep = json.loads(response3.content)
            reps= rep["uniqueObject"]["siteRanges"]
            # 验证alert是否绑定成功，使用DataUtils.find_item_by_key查找匹配的siteId元素
            matched_site = DataUtils.find_item_by_key(reps, "siteId", target_site_id)
            
            # 检查是否找到匹配的siteId
            if matched_site is None:
                raise RequestError(f"Site ID {target_site_id} not found in siteRanges.")
            # 检查alertid在record_detail页，且排序在最下
            Assertions.assert_equal(matched_site["uniqueObjectItems"][-1]["alertId"], target_alert_id)

            # 验证绑定成功后，解绑
            rec_data_2 = {
                "alertId": target_alert_id,
                "isRelate": False,
                "recordId": record_id
            }
            response2 = api_instance.send(endpoint_path="asset_tracking_alert_relate", method="POST", is_valid=True, data=rec_data_2)
            Assertions.assert_status_code(response2, 200)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_alert_face_search_success(self):
        """
        POST    
        alert face search
        Success
        :param input_data:
        :return:
        """
        # 这个用例写的是alert tab页的face search功能；face search中的search by name用例写在test_database.py中的search_face_record
        s3_key, yolo_data = api_instance.prepare_data_for_record("human")
        record_data = {
            "embedding": yolo_data[0]["faceEmbedding"],
            "paging": {
                "limit": 20
            },
            "snapshot_req": {
                "width": 1024
            },
            "sortByTime": False,
            "threshold": 0.85,
            "trackingId": "",
            "version": "face_v1",
            "withLicense": True,
            "withLocation": True
        }          
        try:         
            # 拿到embedding后，查询面部识别出来的alert
            response = api_instance.send(endpoint_path="alert_alerts_search", method="POST", is_valid=True, data = record_data)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_alert_image_search_success(self):
        """
        POST    
        alert image search
        Success
        :param input_data:
        :return:
        """
        s3_key, yolo_data = api_instance.prepare_data_for_record("human")      
        datas = {
            "embedding": "",
            "imageUrl": s3_key,
            "paging": {
                "limit": 20
            },
            "snapshot_req": {
                "width": 1024
            },
            "sortByTime": False,
            # "startedAt": cls.start_time,
            "threshold": -0.6,
            "trackingId": "",
            "version": "image_v1",
            "withLicense": True,
            "withLocation": True
        }            
        try:         
            response = api_instance.send(endpoint_path="alert_alerts_search", method="POST", is_valid=True, data = datas)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")