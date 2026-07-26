import pytest
import arrow
from src.api.client import api_instance
from src.core.api_exceptions import RequestError
from src.utils.assertions import Assertions

class TestUsage:

    @pytest.mark.P1
    @pytest.mark.parametrize("classes", ["A", "B", "C"])
    def test_get_ai_credit_usage(self, classes):
        """
        测试获取 AI 积分使用情况
        """
        # 构建查询参数
        now = arrow.now()
        params = {
            "startedAt": now.floor('month').format('YYYYMMDD'),
            "endedAt": now.ceil('month').format('YYYYMMDD'),
            "classes": classes
            }
        
        try:
            response = api_instance.send(endpoint_path="ai_metrics", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)
        except Exception as e:
            raise RequestError(f"Error while get usage: {str(e)}")