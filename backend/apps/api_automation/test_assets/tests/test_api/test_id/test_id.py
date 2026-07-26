import json
import pytest
import datetime
import time
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.core.logger import logger
from src.data.params import POST_PARAMS, GET_PARAMS
from src.data.faker import faker

class TestId:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        logger.info("\nPreparing...")
        #TODO prepare id alert

        # 获取当天零点时间戳（秒）
        timestamps = faker.generate_timestamps_in_period(unit="day", precision="s")
        cls.today_timestamp_start = timestamps[0]
        cls.today_timestamp_end = timestamps[1]

        # 获取当天的id 列表，并取到id数据用于后续测试
        # 若当天没有id产生，则测试将会失败，需要增加前置操作创建id，todo
        data = {}
        data["start"] = cls.today_timestamp_start
        data["end"] = cls.today_timestamp_end
        id_response = api_instance.send(endpoint_path="id_ids_cars_search", method="POST", is_valid=True, data=data)
        if id_response.status_code != 200:
            pytest.skip(f"ID 测试数据不可用，查询接口返回 {id_response.status_code}。")
        rep_case = json.loads(id_response.content)
        if len(rep_case["uniqueObjectSummaryList"]) > 0:
            cls.id_0_metadata = rep_case["uniqueObjectSummaryList"][0]
            cls.id = rep_case["uniqueObjectSummaryList"][0]["id"]
            cls.uniqueValue = rep_case["uniqueObjectSummaryList"][0]["uniqueKey"]["uniqueValue"]
            cls.detectedTimes = rep_case["uniqueObjectSummaryList"][0]["detectedTimes"]
            cls.databaseName = rep_case["uniqueObjectSummaryList"][0]["databaseName"]
            cls.recordName = rep_case["uniqueObjectSummaryList"][0]["recordName"]
            logger.info("\nid found success,test start.")
            logger.info("\nPrepared...")
        else:
            # todo，增加前置操作创建id
            pytest.exit("No id found for the current day. All tests in this file are skipped.")
        
    @pytest.mark.P0
    def test_post_id_ids_cars_search_success(self):
        """
        POST  
        search id 
        Success
        :param
        :return:
        """
        data = {}
        data["start"] = self.today_timestamp_start
        data["end"] = self.today_timestamp_end
        try:
            response = api_instance.send(endpoint_path="id_ids_cars_search", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["uniqueObjectSummaryList"])
            Assertions.assert_equal(rep["uniqueObjectSummaryList"][0]["id"], self.id)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")

    @pytest.mark.P0
    def test_post_id_ids_cars_search_car_license_success(self):
        """
        POST  
        search car license
        Success
        :param
        :return:
        """
        data = {}
        data["start"] = self.today_timestamp_start
        data["end"] = self.today_timestamp_end
        data["lpn"] = self.uniqueValue
        try:
            response = api_instance.send(endpoint_path="id_ids_cars_search", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["uniqueObjectSummaryList"])
            Assertions.assert_equal(rep["uniqueObjectSummaryList"][0]["uniqueKey"]["uniqueValue"], self.uniqueValue)
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}") 

    @pytest.mark.P0
    def test_get_id_ids_detail_success(self):
        """
        GET 
        id detail
        Success
        :param
        :return:
        """
        param = {"dateTimestamp": ""}
        try:
            # 查询第一个id的详情
            response = api_instance.send(endpoint_path="id_ids_id", method="GET", is_valid=True, params=param, id = self.id)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["uniqueObject"])
        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}") 

    @pytest.mark.P0
    def test_post_edit_id_ids_success(self):
        """
        POST 
        id ids
        Success
        :param
        :return:
        """
        # edit id 和link to database 一起
        random_car_license = faker.generate_license_plate()
        data = {}
        data["value"] = random_car_license
        try:
            # edit id
            response = api_instance.send(endpoint_path="id_ids_id", method="POST", is_valid=True, data=data, id = self.id)
            Assertions.assert_status_code(response, 200)

            data = {}
            data["start"] = self.today_timestamp_start
            data["end"] = self.today_timestamp_end
            # verify id edit success
            response = api_instance.send(endpoint_path="id_ids_cars_search", method="POST", is_valid=True, data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_not_empty(rep["uniqueObjectSummaryList"])
            # 遍历uniqueObjectSummaryList中的每个元素，检查random_car_license是否存在于uniqueKey.uniqueValue中
            found = False
            for item in rep["uniqueObjectSummaryList"]:
                if item["uniqueKey"]["uniqueValue"] == random_car_license:
                    found = True
                    break
            Assertions.assert_true(found, f"Expected random_car_license '{random_car_license}' not found in uniqueObjectSummaryList's uniqueKey.uniqueValue")

            # 先遍历database,找到car record,再link到database            
            response = api_instance.send(endpoint_path="asset_tracking_databases", method="GET", is_valid=True, params={})
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            matched_record = False
            for database in rep["databases"]:
                database_id = database["id"]
                # 查询databse下的所有record
                param = {
                    "search": "",
                    "trackingGroupId": database_id,
                    "type": "car"
                    }
                response2 = api_instance.send(endpoint_path="asset_tracking_records",
                                          method="GET", is_valid=True, params = param)
                rep2 = json.loads(response2.content)
                if len(rep2["records"]) > 0:
                    matched_record = True
                    record_id = rep2["records"][0]["id"]
                    break
            # 循环完成后检查是否找到匹配的record
            if not matched_record:
                pytest.skip("Could not find a record with type 'car' to link.")
            else:
                # 只有未link过的id才能link,所以要前置修改id确保id未link,然后link到database
                # id 的record link 到同一record只能link一次，改变id后再link到database也不行，因此本用例在没有新的id产生的情况下仅可跑一次；
                data = {}
                data["recordId"] = record_id
                data["uniqueObjectId"] = self.id
                response = api_instance.send(endpoint_path="asset_tracking_unique_object_relate", method="POST", is_valid=True, data=data)
                Assertions.assert_status_code(response, 200)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")