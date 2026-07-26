import pytest
import arrow
from pprint import pprint
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions

class TestStats:
    @classmethod
    def setup_class(cls):
        """在整个测试类开始之前执行的动作"""
        site_info = api_instance.dealer_data.get("sites", {})
        if site_info:
            cls.site_id = site_info.get("id")
            cls.site_tz = site_info.get("timezone")
        else:
            pytest.skip("No site info found, skipping tests...")
        print("\nSetting up TestAPI class...")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        print("\nTearing down TestAPI class...")

    @pytest.mark.P1
    @pytest.mark.parametrize("dimensions", ["StatsGender", "StatsAge", "StatsHolding", "StatsActivity"])
    def test_get_stats_query(self, dimensions):
        """
        测试获取统计查询结果
        """
        # 构建查询参数
        now = arrow.now()
        params = {
            "startTime": now.floor('month').format('YYYY-MM-DD HH:mm:ss'),
            "endTime": now.ceil('month').format('YYYY-MM-DD HH:mm:ss'),
            "timezone": self.site_tz,
            "siteId": self.site_id,
            "dimensions": dimensions,
            "granularity": "StatMonth"
            }
        
        try:
            response = api_instance.send(endpoint_path="stats_query", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)
            res = response.json()
            if not res.get("list"):
                pytest.skip("当前环境没有可用于统计查询的数据。")
            stats_data = res.get("list")[0].get("stats")
            dim = str(dimensions).lower().replace("stats", "")
            Assertions.assert_in(dim, stats_data)
        except Exception as e:
            raise RequestError(f"Error while get stats_query: {str(e)}")
