# -*- coding: utf-8 -*-
import json
import pytest
from pathlib import Path
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker
from src.utils.data_utils import DataUtils

class TestDatabase:
    
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        print("\nSetting up TestAPI class...")
        
    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.fixture
    def fixture_database_curd(self):
        generator = self.database_curd()
        gen_data = next(generator)
        yield gen_data
        try:
            next(generator)
        except StopIteration:
            pass
    
    def database_curd(self):
        # create database
        data = {
            "database": {
                "description": "",
                "name": "autotest_database"
            }
        }
        try:
            response = api_instance.send(endpoint_path="asset_tracking_database", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)

            param = {"name": "autotest_database"}
            # get database
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=param)
            rep_2 = json.loads(response_2.content)
            Assertions.assert_status_code(response_2, 200)
            Assertions.assert_not_empty(rep_2)
            Assertions.assert_equal(rep_2["databases"][-1]["name"], "autotest_database")
            Assertions.assert_equal(rep_2["databases"][-1]["description"], "")
            
            first_trackingGroupId = rep_2["databases"][-1]["id"]
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        yield first_trackingGroupId
        
        # updata database
        data = {
            "database": {
                "description": "updated description",
                "id": first_trackingGroupId,
                "name": "autotest_database_2"
            }
        }
        try:
            response_update = api_instance.send(endpoint_path="asset_tracking_database", method="POST", is_valid=True, data=data)
            rep_up = json.loads(response_update.content)
            Assertions.assert_status_code(response_update, 200)

            # check database update
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True)
            rep_2 = json.loads(response_2.content)
            Assertions.assert_status_code(response_2, 200)
            Assertions.assert_not_empty(rep_2)
            Assertions.assert_equal(rep_2["databases"][-1]["name"], "autotest_database_2")
            Assertions.assert_equal(rep_2["databases"][-1]["description"], "updated description")
            Assertions.assert_equal(rep_2["databases"][-1]["id"], first_trackingGroupId)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # delete database
        try:
            response_3 = api_instance.send(endpoint_path="asset_tracking_database_id", method="DELETE", is_valid=True, id=first_trackingGroupId)
            Assertions.assert_status_code(response_3, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    
    @pytest.mark.P1
    def test_database_curd_success(self):
        """
        test database creation / read / update / deletion success
        steps:
            1. create database
            2. get databases
            3. update database and check update
            4. delete database
        """
        self.database_curd()

    @pytest.mark.P1
    @pytest.mark.parametrize("record_type", ["human", "car"])    
    def test_record_curd_success(self, fixture_database_curd, record_type):
        """ 
        test record creation / read / update / deletion success
        test setup: create database
        test teardown: delete database
        steps:
            1. create record
            2. get records
            3. update record and check update
            4. delete record
        """
        self.first_trackingGroupId = fixture_database_curd
        # create record
        s3_key, yolo_data = api_instance.prepare_data_for_record(record_type)
        data = {
            "name": f"autotest_record_{record_type}",
            "s3Key": s3_key,
            "trackingGroupId": self.first_trackingGroupId,
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
                    "trackingGroupId": self.first_trackingGroupId,
                }
            }
        try:
            response_3 = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response_3, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # get records
        param = {"search": f"autotest_record_{record_type}"}
        try:
            response_4 = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records", 
                                          method="GET", is_valid=True, trackingGroupId=self.first_trackingGroupId, params=param)
            rep_4 = json.loads(response_4.content)
            Assertions.assert_status_code(response_4, 200)
            Assertions.assert_not_empty(rep_4)
            Assertions.assert_equal(rep_4["records"][-1]["name"], f"autotest_record_{record_type}")
            Assertions.assert_equal(rep_4["records"][-1]["trackingGroupId"], self.first_trackingGroupId)
            Assertions.assert_equal(rep_4["records"][-1]["type"], record_type)
            Assertions.assert_true(rep_4["records"][-1]["image"].get("key", "").startswith("org"))
            if record_type == "human":
                Assertions.assert_equal(rep_4["records"][-1]["human"]["boundingBox"], yolo_data[0]["boundingBox"])
                Assertions.assert_equal(rep_4["records"][-1]["human"]["faceEmbedding"], yolo_data[0]["faceEmbedding"])
            elif record_type == "car":
                Assertions.assert_equal(rep_4["records"][-1]["car"]["boundingBox"], yolo_data[0]["boundingBox"])
                Assertions.assert_equal(rep_4["records"][-1]["car"]["lpr"]["licensePlate"], yolo_data[0]["plateNumber"])
             
            self.rec_meta = rep_4["records"][-1]
            self.rec_id = rep_4["records"][-1]["id"]
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # update record
        self.rec_meta["name"] = "autotest_record_2"
        self.rec_meta["s3Key"] = self.rec_meta.get("image", {}).get("key", "")
        try:
            response_update = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=self.rec_meta)
            Assertions.assert_status_code(response_update, 200)
            # check update
            response_check = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records", 
                                          method="GET", is_valid=True, trackingGroupId=self.first_trackingGroupId)
            rep_ck = json.loads(response_check.content)
            Assertions.assert_equal(rep_ck["records"][-1]["id"], self.rec_meta["id"])
            Assertions.assert_equal(rep_ck["records"][-1]["name"], self.rec_meta["name"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # delete record
        try:
            response_5 = api_instance.send(endpoint_path="asset_tracking_record_id", method="DELETE", is_valid=True, id=self.rec_id)
            rep_5 = json.loads(response_5.content)
            Assertions.assert_status_code(response_5, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P1
    def test_modification_of_databases_and_records(self, fixture_database_curd):
        """
        Test database operation with records
        steps:
            1. Create database A and B
            2. Create 1 record under the database A
            3. Change the record under database A to database B
            4. Check the databases and record numbers of them
            5. Delete database B
        """
        self.first_trackingGroupId = fixture_database_curd
        # create database B
        data = {
            "database": {
                "description": "",
                "name": "autotest_database_B"
            }
        }
        try:
            response = api_instance.send(endpoint_path="asset_tracking_database", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            
            # get database
            param = {"name": "autotest_database_B"}
            response_2 = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params=param)
            Assertions.assert_status_code(response_2, 200)
            rep_2 = json.loads(response_2.content)
            Assertions.assert_equal(rep_2["databases"][-1]["name"], "autotest_database_B")
            self.second_trackingGroupId = rep_2["databases"][-1]["id"]

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

        # create record
        rec_name = faker.generate_name()
        data = {
                "name": rec_name,
                "trackingGroupId": self.first_trackingGroupId,
                "car": {
                    "boundingBox": {},
                    "lpr": {
                        "licensePlate": faker.generate_license_plate(),
                        "name": rec_name,
                        "trackingGroupId": self.first_trackingGroupId
                    }
                },
                "type": "car"
            }
        try:
            response_3 = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response_3, 200)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        # get records
        param = {"search": rec_name}
        try:
            response_4 = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=self.first_trackingGroupId, params=param)
            rep_4 = json.loads(response_4.content)
            Assertions.assert_status_code(response_4, 200)
            Assertions.assert_not_empty(rep_4)
            Assertions.assert_equal(rep_4["records"][-1]["name"], rec_name)
            self.rec_meta = rep_4["records"][-1]
            self.rec_id = rep_4["records"][-1]["id"]

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
        # change record to database B
        self.rec_meta["trackingGroupId"] = self.second_trackingGroupId
        try:
            response_update = api_instance.send(endpoint_path="asset_tracking_record", method="POST", is_valid=True, data=self.rec_meta)
            Assertions.assert_status_code(response_update, 200)
            # check record update
            response_check = api_instance.send(endpoint_path="asset_tracking_database_trackingGroupId_records",
                                          method="GET", is_valid=True, trackingGroupId=self.second_trackingGroupId, params=param)
            rep_ck = json.loads(response_check.content)
            Assertions.assert_equal(rep_ck["records"][-1]["name"], rec_name)
            Assertions.assert_equal(rep_ck["records"][-1]["trackingGroupId"], self.second_trackingGroupId)
            # check database record number
            response_all = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True)
            Assertions.assert_status_code(response_all, 200)
            rep_all = json.loads(response_all.content)
            res = DataUtils.find_item_by_key(data=rep_all, key="id", value=self.second_trackingGroupId, return_parent=False)
            Assertions.assert_equal(res["name"], "autotest_database_B")
            Assertions.assert_equal(res["recordCount"], 1)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

        # delete database B
        try:
            response_5 = api_instance.send(endpoint_path="asset_tracking_database_id", method="DELETE", is_valid=True, id=self.second_trackingGroupId)
            Assertions.assert_status_code(response_5, 200)
            
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")