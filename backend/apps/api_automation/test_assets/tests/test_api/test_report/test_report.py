# -*- coding: utf-8 -*-
import json
import pytest
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions
from src.data.faker import faker

class TestReport:
    
    @pytest.mark.P0
    def test_get_get_case_report_success(self):
        """
        GET case_reports
        success
        :param
        :return:
        """
        timestamps = faker.generate_timestamps_in_period(unit="day", precision="ms")
        param = {
            "startedAt": timestamps[0],
            "endedAt": timestamps[1]
        }
        try:
            response = api_instance.send(endpoint_path="case_reports", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_not_empty(rep)

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")
        
    @pytest.mark.P0
    def test_get_get_daily_case_report_success(self):
        """
        GET case_daily_reports
        success
        :param
        :return:
        """
        timestamps = faker.generate_timestamps_in_period(unit="month", precision="ms")
        param = {
            "startedAt": timestamps[0],
            "endedAt": timestamps[1]
        }
        try:
            response = api_instance.send(endpoint_path="case_daily_reports", method="GET", is_valid=True, params=param)
            rep = json.loads(response.content)
            Assertions.assert_status_code(response, 200)
            Assertions.assert_contains_key(rep, "$", "dailyCases")

        except Exception as e:
            raise RequestError(f"An unexpected error occurred: {str(e)}")