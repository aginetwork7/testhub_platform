# -*- coding: utf-8 -*-
import json
import pytest
from pathlib import Path
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.core.config import config
from src.core.logger import logger
from src.utils.data_utils import DataUtils
import random

class TestDatabase:
    _data_cache = {}
    enable_local_cache = config.get("api.database.enable_local_cache", False)
    _cache_file = Path(config.get("test.data.db_cache_file", "data/database/cache.yaml"))
    
    @classmethod
    def setup_class(cls):
        if cls.enable_local_cache:
            global api_instance
            cls._data_cache = api_instance._load_cache(cls._cache_file)
        """在整个测试类开始之前执行的动作"""
        cls.post_db1_data = {
            "database": {
                "description": "",
                "name": "autotest_database"
            }
        }
        cls.get_db1_param  = {
            "name": "autotest_database"
        }
        print("\nSetting up TestAPI class...")
        
    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        if cls.enable_local_cache:
            global api_instance
            api_instance._save_cache(cls._data_cache, cls._cache_file)
        print("\nTearing down TestAPI class...")  


    @classmethod
    def create_database(cls, post_data):
        try:
            response_1 = api_instance.send(endpoint_path="asset_tracking_database", method="POST", is_valid=True, data=post_data)
            Assertions.assert_status_code(response_1, 200)

            # get database
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=cls.get_db1_param)
            Assertions.assert_status_code(response_2, 200)
            rep_ck = json.loads(response_2.content)
            
            return rep_ck
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @classmethod
    def delete_database(cls, trackingGroupId):
        try:
            response_1 = api_instance.send(endpoint_path="asset_tracking_database_id", method="DELETE", is_valid=True, id=trackingGroupId)
            Assertions.assert_status_code(response_1, 200)
            # get database
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=cls.get_db1_param)
            Assertions.assert_status_code(response_2, 200)
            rep_ck = json.loads(response_2.content)
            
            return rep_ck
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @classmethod
    def update_database(cls, update_data):
        try:
            response_update = api_instance.send(endpoint_path="asset_tracking_database", method="POST", is_valid=True, data=update_data)
            Assertions.assert_status_code(response_update, 200)
    
            # check database update
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True)
            Assertions.assert_status_code(response_2, 200)
            rep_2 = json.loads(response_2.content)
            
            return rep_2

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    # get databases
    @classmethod
    def get_databases(cls, name):
        param = {
            "name": name
        }
        try:
            response = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=param)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            return rep
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")   

    @pytest.fixture()
    def fixture_database_create_and_delete(self):
        rep_ck = self.create_database(post_data=self.post_db1_data)
        yield rep_ck
        self.delete_database(rep_ck["databases"][-1]["id"])

    @classmethod
    def create_record(cls, record_type, db_info, isCritical=False):
        db1_trackingGroupId = db_info["databases"][-1]["id"]
        s3_key, yolo_data = api_instance.prepare_data_for_record(
            record_type=record_type,
            data_cache=cls._data_cache,
            enable_local_cache=cls.enable_local_cache
        )
        data = {
            "name": f"autotest_record_{record_type}",
            "isCritical": isCritical,
            "s3Key": s3_key,
            "trackingGroupId": db1_trackingGroupId,
            "type": record_type
        }
        
        if record_type == "human":
            data["human"] = {
                    "boundingBox": yolo_data[0]["boundingBox"],
                    "faceEmbedding": yolo_data[0]["faceEmbedding"]
                }
        elif record_type == "car":
            data["car"] = {
                "boundingBox": yolo_data[0]["boundingBox"],
                "lpr": {
                    "img": {
                        "key": s3_key,
                        "url": yolo_data[0]["url"]
                    },
                    "licensePlate": yolo_data[0]["plateNumber"],
                    "name": "autotest_record_car",
                    "trackingGroupId": db1_trackingGroupId,
                }
            }
        try:
            response_1 = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response_1, 200)
            
            response_2 = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records", 
                                          method="GET", is_valid=True, trackingGroupId=db1_trackingGroupId)
            Assertions.assert_status_code(response_2, 200)
            rep_2 = json.loads(response_2.content)
            return rep_2
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @classmethod
    def delete_record(cls, trackingGroupId, rec_id):
        try:
            response = api_instance.send(endpoint_path="asset_tracking_record_id", method="DELETE", is_valid=True, id=rec_id)
            Assertions.assert_status_code(response, 200)
            
            response_2 = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=trackingGroupId)
            Assertions.assert_status_code(response_2, 200)
            rep_2 = json.loads(response_2.content)
            return rep_2
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
    
    @classmethod
    def search_face_record(cls, trackingId):
        record_data = {
            "embedding": "",
            "paging": {
                "limit": 20
            },
            "snapshot_req": {
                "width": 1024,
            },
            "sortByTime": False,
            "threshold": 0.85,
            "trackingId": trackingId,
            "version": "face_v1",
            "withLicense": True,
            "withLocation": True
        }
        try:
            response = api_instance.send(endpoint_path="alert_alerts_search", method="POST", is_valid=True, data=record_data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            return rep
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @classmethod
    def search_car_record(cls, lpn):
        record_data = {
            "lpn": lpn,
            "page.total": 20,
            "searchFlag": 0
        }
        try:
            response = api_instance.send(endpoint_path="alert_alerts_search_cars", method="POST", is_valid=True, data=record_data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            return rep
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}") 

    @classmethod
    def update_record(cls, rec_meta, trackingGroupId):
        try:
            response_update = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=rec_meta)
            Assertions.assert_status_code(response_update, 200)
            # check update
            response_check = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=trackingGroupId)
            rep_ck = json.loads(response_check.content)
            return rep_ck
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.fixture()
    def fixture_record_create_and_delete(self, request, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete
        record_type = request.param
        rep = self.create_record(record_type, db_info)
        trackingGroupId = rep["records"][-1]["trackingGroupId"]
        rec_id = rep["records"][-1]["id"]
        yield rep
        self.delete_record(trackingGroupId, rec_id)        

    @pytest.mark.P0
    @pytest.mark.parametrize("input_data", [
            {
                "database": {
                    "description": "",
                    "name": "autotest_database"
                }
            }
        ]) 
    def test_post_create_database_success(self, input_data):
        # 生成随机数并更新数据库名称
        random_int = random.randint(1, 10000)
        input_data["database"]["name"] = f"{input_data['database']['name']}_{random_int}"
        # create database,分别验证Unified database 和普通database
        # 目前只有pd customer才有权限新建Unified database，但pd角色不可更改，此处删除原pd相关用例
        try:
            rep_ck = self.create_database(post_data=input_data)
            db1_trackingGroupId = rep_ck["databases"][-1]["id"]
            Assertions.assert_not_empty(rep_ck)
            Assertions.assert_equal(rep_ck["databases"][-1]["name"], input_data["database"]["name"])
            Assertions.assert_equal(rep_ck["databases"][-1]["description"], input_data["database"]["description"])
        except Exception as e:
            raise RequestError(f"Fail to create dababase: {str(e)}")
        finally:  
            self.delete_database(db1_trackingGroupId)

    @pytest.mark.P0
    @pytest.mark.parametrize("name", ["", "autotest_database"])
    def test_get_get_database_success(self, name, fixture_database_create_and_delete):
        # create database
        rep_ck = fixture_database_create_and_delete
        # get database
        try:
            rep = self.get_databases(name)
            Assertions.assert_not_empty(rep)
            Assertions.assert_equal(rep_ck["databases"][-1]["name"], self.post_db1_data["database"]["name"])
            Assertions.assert_equal(rep_ck["databases"][-1]["description"], self.post_db1_data["database"]["description"])
            Assertions.assert_equal(rep_ck["databases"][-1]["recordCount"], 0)
            db1_trackingGroupId = rep_ck["databases"][-1]["id"]
        except Exception as e:
            raise RequestError(f"Fail to get databases: {str(e)}")

    @pytest.mark.P0
    def test_post_update_database_success(self):
        rep = self.create_database(post_data=self.post_db1_data)        
        db1_trackingGroupId = rep["databases"][-1]["id"]
        # update database
        updata_data = {
            "database": {
                "id": db1_trackingGroupId,
                "name": "autotest_database_2"
            }
        }
        try:
            rep_ck = self.update_database(updata_data)
            Assertions.assert_equal(rep_ck["databases"][-1]["name"], "autotest_database_2")
            Assertions.assert_equal(rep_ck["databases"][-1]["recordCount"], 0)
        except Exception as e:
            raise RequestError(f"Fail to update database: {str(e)}")
        finally:
            self.delete_database(db1_trackingGroupId)
            
    @pytest.mark.P0
    def test_post_delete_database_success(self):
        rep = self.create_database(post_data=self.post_db1_data)
        db1_trackingGroupId = rep["databases"][-1]["id"]
        # delete database
        try:
            rep_ck = self.delete_database(db1_trackingGroupId)
            if len(rep_ck["databases"]) > 0:
                res = DataUtils.find_item_by_key(data=rep_ck["databases"], key="id", value=db1_trackingGroupId)
                Assertions.assert_false(res)
        except Exception as e:
            raise RequestError(f"Fail to delete database: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("record_type", ["human", "car"])   
    def test_post_create_record_success(self, record_type, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete
        # create record
        try:
            rep_ck = self.create_record(record_type, db_info)
            Assertions.assert_not_empty(rep_ck)
            
            trackingGroupId = rep_ck["records"][-1]["trackingGroupId"]
            rec_id = rep_ck["records"][-1]["id"]
            
            Assertions.assert_equal(rep_ck["records"][-1]["name"], f"autotest_record_{record_type}")
            Assertions.assert_true(str(rep_ck["records"][-1]["image"]["key"]).startswith("org/"))
            Assertions.assert_not_empty(rep_ck["records"][-1]["image"]["url"])
            Assertions.assert_equal(rep_ck["records"][-1]["type"], record_type)
            
        except Exception as e:
            raise RequestError(f"Fail to create record: {str(e)}")
        finally:
            self.delete_record(trackingGroupId, rec_id)

    @pytest.mark.P0
    @pytest.mark.parametrize("record_type", ["human", "car"])   
    def test_post_create_critical_record_success(self, record_type, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete
        trackingGroupId = None
        rec_id = None
        # create record
        try:
            # 新建critical record
            self.create_record(record_type, db_info, isCritical=True)
            
            # 获取创建的记录信息
            trackingGroupId = db_info["databases"][-1]["id"]
            response = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                       method="GET", is_valid=True, trackingGroupId=trackingGroupId)
            rep_ck = json.loads(response.content)
            Assertions.assert_not_empty(rep_ck)
            
            # 获取最新创建的记录
            latest_record = rep_ck["records"][-1]
            # print(f"latest_record: {latest_record}")
            rec_id = latest_record["id"]
            
            # 验证记录是否包含isCritical=True
            Assertions.assert_has_value(latest_record, "isCritical", True)
            Assertions.assert_equal(latest_record["name"], f"autotest_record_{record_type}")
            Assertions.assert_true(str(latest_record["image"]["key"]).startswith("org/"))
            Assertions.assert_not_empty(latest_record["image"]["url"])
            Assertions.assert_equal(latest_record["type"], record_type)
            
        except Exception as e:
            raise RequestError(f"Fail to create record: {str(e)}")
        finally:
            # 只有当变量被赋值后才执行删除操作
            if trackingGroupId and rec_id:
                self.delete_record(trackingGroupId, rec_id)
        
    @pytest.mark.P0
    @pytest.mark.parametrize("fixture_record_create_and_delete", ["human", "car"], indirect=True)
    def test_post_update_record_success(self, fixture_record_create_and_delete):
        # update record
        rec_metas = fixture_record_create_and_delete
        rec_meta = rec_metas["records"][-1]
        rec_meta["name"] = "autotest_record_2"
        rec_meta["s3Key"] = rec_meta.get("image", {}).get("key", "")
        try:
            rep_ck = self.update_record(rec_meta, rec_meta["trackingGroupId"])
            Assertions.assert_equal(rep_ck["records"][-1]["id"], rec_meta["id"])
            Assertions.assert_equal(rep_ck["records"][-1]["name"], rec_meta["name"])
        except Exception as e:
            raise RequestError(f"Fail to update record: {str(e)}")


    @pytest.mark.P0
    @pytest.mark.parametrize("record_type", ["human", "car"])
    def test_post_search_human_car_record_success(self, record_type, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete
        try:
            rep_ck = self.create_record(record_type, db_info)

            record_id = rep_ck["records"][-1]["id"]
            trackingId = record_id

            if record_type == "car":
                rep_ck2 = self.search_car_record(trackingId)
            else:
                rep_ck2 = self.search_face_record(trackingId)
            Assertions.assert_not_empty(rep_ck2)

        except Exception as e:
            raise RequestError(f"Fail to search car record: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("record_type", ["human", "car"])
    def test_post_delete_record_success(self, record_type, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete
        rep = self.create_record(record_type, db_info)
        Assertions.assert_not_empty(rep)
        trackingGroupId = rep["records"][-1]["trackingGroupId"]
        rec_id = rep["records"][-1]["id"]
        # delete record
        try:
            rep_ck = self.delete_record(trackingGroupId, rec_id)
            if len(rep_ck["records"]) > 0:
                res = DataUtils.find_item_by_key(data=rep_ck["records"], key="id", value=rec_id)
                Assertions.assert_false(res)
        except Exception as e:
            raise RequestError(f"Fail to delete record: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("fixture_record_create_and_delete", ["human", "car"], indirect=True)
    def test_get_records_success(self, fixture_record_create_and_delete):
        # 查询接口是 /asset_tracking/database/{trackingGroupId}/records
        rec_metas = fixture_record_create_and_delete
        rec_meta = rec_metas["records"][-1]
        trackingGroupId = rec_meta["trackingGroupId"]
        rec_type = rec_meta["type"]
        # get records
        param = {"search": "autotest"}
        try:
            response = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=trackingGroupId, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_not_empty(rep)
            Assertions.assert_equal(rep["records"][-1]["name"], f"autotest_record_{rec_type}")
        except Exception as e:
            raise RequestError(f"Fail to get records: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("name", [""])
    def test_get_database_records_success(self, name):
        # get database records，和上面的查询接口不一样，alert linkto database时的查询接口是/asset_tracking/records
        try:
            rep = self.get_databases(name)
            Assertions.assert_not_empty(rep)
            database_id = rep["databases"][0]["id"]
            param = {
                "type": "human",
                "search": name,
                "trackingGroupId": database_id
            }
            response = api_instance.send(endpoint_path="asset_tracking_records", method="GET", is_valid=True, params=param)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep)

        except Exception as e:
            raise RequestError(f"Fail to get database records: {str(e)}")

    @pytest.mark.P0
    @pytest.mark.parametrize("record_type", ["human", "car"])
    def test_get_record_detail_success(self, record_type, fixture_database_create_and_delete):
        db_info = fixture_database_create_and_delete

        try:
            # create record并查看record detail,此时为空
            rec_metas = self.create_record(record_type, db_info)
            rec_meta = rec_metas["records"][-1]
            record_id = rec_meta["id"]
            param = {"dateTimestamp": ""}

            response = api_instance.send(endpoint_path="asset_tracking_record_detail_id",
                                          method="GET", is_valid=True, id=record_id, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_not_empty(rep)
        except Exception as e:
            raise RequestError(f"Fail to get records: {str(e)}")

    @pytest.mark.P0
    def test_get_record_case_list_success(self):
        """
        get
        record case list
        Success
        :param input_data:
        :return:
        """
        try:
            # 先查询记录下当前所有的database
            rep1 = self.get_databases("")
            Assertions.assert_not_empty(rep1)
            
            # 遍历所有database，找到任意一个满足条件linkedCaseCount > 0的record就退出循环
            # 目的是查找到关联alert 处理为case非空的record，然后查询这个record的linkedcase
            matched_record = None
            # 先遍历database
            for database in rep1["databases"]:
                database_id = database["id"]
                # 查询databse下的所有record
                param = {"search": ""}
                response2 = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=database_id, params = param)
                rep2 = json.loads(response2.content)

                # 遍历record，查找满足linkedCaseCount > 0的record，并返回对应的record id
                for record in rep2["records"]:
                    # 拿到record去查询record_detail，因为detail页才有linkedCaseCount属性
                    param = {"dateTimestamp": ""}
                    response3 = api_instance.send(endpoint_path="asset_tracking_record_detail_id",
                                            method="GET", is_valid=True, id=record["id"], params=param)
                    rep3 = json.loads(response3.content)
                    detect_times = rep3["linkedCaseCount"]
                    # 查找第一个满足detect_times > 0的record
                    if detect_times > 0:
                        matched_record = record
                        logger.info(f"find needed record: {matched_record['id']}")
                        # 找到满足条件的record，立即跳出内循环
                        break              
                # 如果在内循环中找到了匹配的record，跳出外循环
                if matched_record:
                    break
            # 循环完成后检查是否找到匹配的record
            if not matched_record:
                pytest.skip("Could not find a record with linkedCaseCount > 0 to run the test.")
            else:
                # 查看该record的 record case list
                param = {"trackingRecordId": matched_record["id"]}
                response4 = api_instance.send(endpoint_path="asset_tracking_record_case_list",
                                            method="GET", is_valid=True, params=param)
                
                Assertions.assert_status_code(response4, 200)
                rep4 = json.loads(response4.content)
                # 验证record case list的长度是否等于linkedCaseCount
                Assertions.assert_equal(detect_times, len(rep4["caseList"]))
        except Exception as e:
            raise RequestError(f"Fail to get record case list: {str(e)}")
