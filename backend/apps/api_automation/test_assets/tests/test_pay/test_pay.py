# -*- coding: utf-8 -*-
import json
import time

import pytest
from src.api.client import api_instance
from src.utils.assertions import Assertions
from src.utils.data_utils import DataUtils
from src.utils.stripe_utils import StripePaymentService




def refresh_camera_dealer_data(return_cameras_only=True):
    """
    2. 清除 dealer_data 缓存（确保使用新权限加载）。
    3. 强制重新加载 dealer_data。
    4. 根据参数返回完整的 dealer_data 或 cameras 列表。

    :param return_cameras_only: (可选) 如果为 True，则只返回 'cameras' 列表；否则返回完整的 dealer_data 字典。默认为 True。
    :return: 完整的 dealer_data 字典 或 cameras 列表。
    """
    api_instance.login("dealer")
    api_instance.clear_dealer_data_cache()
    dealer_data = api_instance.dealer_data or {}

    if return_cameras_only:
        return dealer_data.get('cameras', [])
    else:
        return dealer_data

def get_camera_by_id(camera_id):
    """
    根据摄像头ID在 dealer_data 中查找并返回对应的摄像头对象。
    使用 refresh_data_for_role 方法确保获取最新的 dealer 数据。

    :param camera_id: 要查找的摄像头ID（通常是字符串或整数）。
    :return: 找到的摄像头对象（字典），如果未找到则返回 None。
    """

    # 关键修改：使用 refresh_data_for_role 来获取最新的 dealer_data
    # 假设获取 dealer 数据时应使用 "dealer" 角色。
    dealer_data = refresh_camera_dealer_data(return_cameras_only=False)

    # 提取 cameras 数据 (如果 dealer_data 是空字典，这里会返回空列表)
    camera_data = dealer_data.get('cameras', [])

    if not camera_data:
        print("错误：cameras 未获取到或为空。")
        return None

    for camera in camera_data:
        # 假设摄像头ID键为 'id'。
        if str(camera.get('id')) == str(camera_id):
            return camera

    return None

class TestPay:

    @classmethod
    def setup_class(cls):
        try:
            cls.cameras = refresh_camera_dealer_data()
            cls.goods_data = api_instance.goods_data

            # 初始化 2 个摄像头
            cls.camera_free = None
            cls.camera_none = None

            for cam in cls.cameras:
                is_free_trial = cam.get("isFreeTrial", False)
                quota_usages = cam.get("quotaUsages", [])

                if is_free_trial and cls.camera_free is None:
                    cls.camera_free = cam

                elif not quota_usages and cls.camera_none is None:
                    cls.camera_none = cam

                else:
                    pass


                if cls.camera_free  and cls.camera_none:
                    break

            # 记录缺失类型
            cls.missing_cameras = []
            if not cls.camera_free:
                cls.missing_cameras.append("free")

            if not cls.camera_none:
                cls.missing_cameras.append("none")

            if cls.missing_cameras:
                print(f"\n警告: 未找到以下类型摄像头: {', '.join(cls.missing_cameras)}，相关用例将被跳过")
            else:
                print(f"\n摄像头初始化成功:")
                print(f"  free: ID={cls.camera_free['id']}")

                print(f"  none: ID={cls.camera_none['id']}")

        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
        finally:
            api_instance.login("DEALER")

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        api_instance.login(api_instance.default_role)
        StripePaymentService.clear_mock_data()
        print("\nTearing down TestAPI class...")

    @classmethod
    def setup_method(cls, method):
        """
        新增：在每个 test_* 方法执行之前执行 (Function-level setup)
        参数 method 是当前即将执行的测试方法对象。
        """
        print(f"\n--- 🛠️ 准备测试方法: {method.__name__} ---")
        # 可以在这里执行一些操作，例如：
        # - 确保数据库连接是干净的。
        # - 重置 API 客户端的特定状态。
        # - 打印测试用例开始标志。
        api_instance.login("DEALER")

    @classmethod
    def teardown_method(cls, method):
        """
        新增：在每个 test_* 方法执行之后执行 (Function-level teardown)
        参数 method 是刚刚执行完毕的测试方法对象。
        """
        print(f"--- ✅ 清理测试方法: {method.__name__} ---")
        # 可以在这里执行一些清理操作，例如：
        # - 清理临时创建的文件或数据库记录。
        # - 确保所有 Mock 状态被清除了。
        pass


    @pytest.mark.P0
    @pytest.mark.pay
    def test_l01_get_license_price_all(self):
        """
        [L01] 获取 License 新购价格 free套餐
        1Y40G
        3Y20G m
        5Y60G
        接口路径: /license/price
        测试目标: 校验新购价格计算是否正确
        验证点: 响应金额与配置匹配
        """

        obj_cameras = [self.camera_free, self.camera_none]
        if not all(obj_cameras):
            pytest.skip("缺少 free / none 任意一种摄像头，跳过测试")
        try:
            units_1_40 = DataUtils.get_selected_config(self.goods_data, storage_str="40 GB")
            units_3_20 = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_cameras[0]["id"],
                        "goodsId": 1,
                        "units": units_1_40
                    },
                    {
                        "targetId": obj_cameras[1]["id"],
                        "goodsId": 1,
                        "units": units_3_20
                    }

                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list(obj_cameras, data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l02_get_license_price_1Y_40G_free(self):
        """
        [L02] 获取 License 新购价格 free套餐
        1Y40G
        接口路径: /license/price
        测试目标: 校验新购价格计算是否正确
        验证点: 响应金额与配置匹配
        """

        if not self.camera_free:
            pytest.skip("未找到 free 摄像头，跳过测试")

        obj_camera = self.camera_free
        try:
            units = DataUtils.get_selected_config(self.goods_data, storage_str="40 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l03_get_license_price_1Y_40G_paid(self):
        """
        [L03] 获取 License 新购价格 已有老订单
        1Y40G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_none:
            pytest.skip("未找到摄像头，跳过测试")

        obj_camera_paid = self.camera_none

        try:
            units_paid = DataUtils.get_selected_config(self.goods_data, year_str="3 yr")
            data_paid = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera_paid["id"],
                        "goodsId": 1,
                        "units": units_paid
                    }
                ],
                "targetType": "target_camera",
            }
            response_paid = api_instance.send(endpoint_path="license_price", method="POST", data=data_paid)
            Assertions.assert_status_code(response_paid, 200)
            rep_paid = json.loads(response_paid.content)
            order_payload = DataUtils.generate_order_payload(data_paid, rep_paid)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")
            time.sleep(3)


            obj_camera = get_camera_by_id(obj_camera_paid["id"])
            if not obj_camera:
                pytest.skip("未找到摄像头，跳过测试")
            units = DataUtils.get_selected_config(self.goods_data, storage_str="40 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            ss.revoke_or_cancel_order()
            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l04_get_license_price_1Y_40G_none(self):
        """
        [L04] 获取 License 新购价格 无license情况
        1Y40G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_none:
            pytest.skip("未找到 none 摄像头，跳过测试")

        obj_camera = self.camera_none

        try:
            units = DataUtils.get_selected_config(self.goods_data, storage_str="40 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l05_get_license_price_5Y_60G_free(self):
        """
        [L05] 获取 License 新购价格 free套餐 打折
        5Y60G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_free:
            pytest.skip("未找到 free 摄像头，跳过测试")

        obj_camera = self.camera_free
        try:
            units = DataUtils.get_selected_config(self.goods_data, year_str="5 yr", storage_str="60 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l06_get_license_price_5Y_60G_paid(self):
        """
        [L06] 获取 License 新购价格 已有老订单 打折
        5Y60G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_none:
            pytest.skip("未找到摄像头，跳过测试")

        obj_camera_paid = self.camera_none

        try:
            units_paid = DataUtils.get_selected_config(self.goods_data, year_str="5 yr")
            data_paid = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera_paid["id"],
                        "goodsId": 1,
                        "units": units_paid
                    }
                ],
                "targetType": "target_camera",
            }
            response_paid = api_instance.send(endpoint_path="license_price", method="POST", data=data_paid)
            Assertions.assert_status_code(response_paid, 200)
            rep_paid = json.loads(response_paid.content)
            order_payload = DataUtils.generate_order_payload(data_paid, rep_paid)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")
            time.sleep(3)


            obj_camera = get_camera_by_id(obj_camera_paid["id"])

            units = DataUtils.get_selected_config(self.goods_data, year_str="5 yr", storage_str="60 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            ss.revoke_or_cancel_order()
            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l07_get_license_price_5Y_60G_none(self):
        """
        [L07] 获取 License 新购价格 无license情况 打折
        5Y60G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_none:
            pytest.skip("未找到 none 摄像头，跳过测试")

        obj_camera = self.camera_none
        try:
            units = DataUtils.get_selected_config(self.goods_data, year_str="5 yr", storage_str="60 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l08_get_license_price_3Y_40G_free_m(self):
        """
        [L08] 获取 License 新购价格 free套餐 打折 加监控
        3Y40G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """

        if not self.camera_free:
            pytest.skip("未找到 free 摄像头，跳过测试")

        obj_camera = self.camera_free
        try:
            units = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", storage_str="40 GB",
                                                  monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l09_get_license_price_3Y_40G_paid_m(self):
        """
        [L09] 获取 License 新购价格 已有老订单 打折 开启监控
        3Y40G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """
        if not self.camera_none:
            pytest.skip("未找到 paid 摄像头，跳过测试")

        obj_camera_paid = self.camera_none

        try:
            units_paid = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", storage_str="60 GB", monitoring_enabled=True)
            data_paid = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera_paid["id"],
                        "goodsId": 1,
                        "units": units_paid
                    }
                ],
                "targetType": "target_camera",
            }
            response_paid = api_instance.send(endpoint_path="license_price", method="POST", data=data_paid)
            Assertions.assert_status_code(response_paid, 200)
            rep_paid = json.loads(response_paid.content)
            order_payload = DataUtils.generate_order_payload(data_paid, rep_paid)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")
            time.sleep(3)
            obj_camera = get_camera_by_id(obj_camera_paid["id"])

            units = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", storage_str="40 GB",
                                                  monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            ss.revoke_or_cancel_order()
            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l10_get_license_price_3Y_40G_none_m(self):
        """
        [L10] 获取 License 新购价格 无license情况 打折 开启监控
        3Y40G
        接口路径: /license/price
        测试目标: 校验新购价格是否正确
        验证点: 响应金额与配置匹配
        """

        if not self.camera_none:
            pytest.skip("未找到 none 摄像头，跳过测试")

        obj_camera = self.camera_none
        try:
            units = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", storage_str="40 GB",
                                                  monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list([obj_camera], data, rep, self.goods_data)

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l11_request_reseller_purchase(self):
        """
        [L11] 请求经销商
        接口路径: /license/ai/request
        测试目标: 验证代购请求提交成功
        验证点: 返回状态 200，字段完整
        """
        try:
            response = api_instance.send(endpoint_path="license_ai_request", method="POST")
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep, {})

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l12_license_activate_status_none_3Y_20G_m(self):
        """
        [L12] License 激活后状态校验（none → paid）
        """
        try:
            if not self.camera_none:
                pytest.skip("未找到 none 摄像头，跳过测试")

            obj_camera = self.camera_none

            units = DataUtils.get_selected_config(self.goods_data, year_str="3 yr",monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }
            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            order_payload = DataUtils.generate_order_payload(data, rep)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")

            camera_data = refresh_camera_dealer_data()
            Assertions.assert_cameras_license_and_monitoring_active(camera_data,obj_camera["id"])

            ss.revoke_or_cancel_order()

            order_rep = ss.get_order_details()
            expected_order_data = {
                "id": ss.local_order_id,
                "status": "confirmed",
                "amount": rep["chargeAmount"],
                "refundAmount": "0",
                "items_count": 1,
                "isRefunded": True,

            }

            Assertions.assert_order_details(order_rep, expected_order_data)


        except AssertionError:

            raise  # 断言失败直接抛

        except Exception as e:
            print(f"Unexpected error: {e}")
            ss.revoke_or_cancel_order()
            raise


    @pytest.mark.pay
    @pytest.mark.P0
    def test_l13_license_activate_status_free_5Y_40G(self):
        """
        [L13] License 激活后状态校验（free → paid）
        """
        try:
            if not self.camera_free:
                pytest.skip("未找到 free 摄像头，跳过测试")

            obj_camera = self.camera_free

            units = DataUtils.get_selected_config(self.goods_data, year_str="5 yr", storage_str="40 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }
            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            order_payload = DataUtils.generate_order_payload(data, rep)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")


            dealer_data =  refresh_camera_dealer_data(return_cameras_only=False)
            Assertions.assert_cameras_license_active( dealer_data.get('cameras', []), obj_camera["id"])


            ss.revoke_or_cancel_order()
            org_id = dealer_data['customers'].get("customer", {}).get("user", {}).get("organization", {}).get("id")
            site_id = dealer_data['sites'].get("id")

        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
        finally:
            api_instance.login("admin")
            free_json = api_instance.apply_free_license(camera_ids=[obj_camera["id"]],org_id=org_id,site_ids=[site_id])
            Assertions.assert_true(obj_camera["id"] in free_json.get("successCameraIds", []),
                                   f"成功摄像头列表中未包含预期的 {obj_camera["id"]}")
            api_instance.login("dealer")

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l14_license_activate_status_paid_1Y_60G(self):
        """
        [L14] License 激活后状态校验（paid → paid）
        """

        try:
            if not self.camera_none:
                pytest.skip("未找到none摄像头，跳过测试")

            obj_camera_paid = self.camera_none
            units_paid = DataUtils.get_selected_config(self.goods_data, year_str="5 yr")
            data_paid = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera_paid["id"],
                        "goodsId": 1,
                        "units": units_paid
                    }
                ],
                "targetType": "target_camera",
            }
            response_paid = api_instance.send(endpoint_path="license_price", method="POST", data=data_paid)
            Assertions.assert_status_code(response_paid, 200)
            rep_paid = json.loads(response_paid.content)
            order_payload = DataUtils.generate_order_payload(data_paid, rep_paid)
            ss_paid = StripePaymentService(order_payload)
            payment_result = ss_paid.pay()
            Assertions.assert_true(payment_result, "pay failed")
            time.sleep(3)

            obj_camera = get_camera_by_id(obj_camera_paid["id"])

            units = DataUtils.get_selected_config(self.goods_data, storage_str="60 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }
            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            order_payload = DataUtils.generate_order_payload(data, rep)
            ss = StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")
            camera_data = refresh_camera_dealer_data()
            Assertions.assert_cameras_license_active(camera_data, obj_camera["id"])

            ss.revoke_or_cancel_order()

        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            ss.revoke_or_cancel_order()
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l15_license_terminate_status(self):
        """
        [L15] License 退订状态校验
        """

        try:
            if not self.camera_none:
                pytest.skip("未找到none摄像头，跳过测试")

            obj_camera_paid = self.camera_none
            units_paid = DataUtils.get_selected_config(self.goods_data)
            data_paid = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera_paid["id"],
                        "goodsId": 1,
                        "units": units_paid
                    }
                ],
                "targetType": "target_camera",
            }
            response_paid = api_instance.send(endpoint_path="license_price", method="POST", data=data_paid)
            Assertions.assert_status_code(response_paid, 200)
            rep_paid = json.loads(response_paid.content)
            order_payload = DataUtils.generate_order_payload(data_paid, rep_paid)
            ss_paid = StripePaymentService(order_payload)
            payment_result = ss_paid.pay()
            Assertions.assert_true(payment_result, "pay failed")
            time.sleep(3)

            obj_camera = get_camera_by_id(obj_camera_paid["id"])

            data = {
                "targetType": "target_camera",
                "targetIdList": [obj_camera["id"]]
            }
            response = api_instance.send(endpoint_path="license_terminate", method="POST", data=data)
            Assertions.assert_status_code(response, 200)

            camera_data = refresh_camera_dealer_data()
            Assertions.assert_cameras_license_inactive(camera_data, obj_camera["id"])

        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise


    @pytest.mark.P0
    @pytest.mark.pay
    def test_l16_goods_type_alert(self):
        """
        [L16] goods_type_alert 查询
        """
        try:
            params = {"goodsType": "goods_type_alert"}
            response = api_instance.send(endpoint_path="goods", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep['goodsInfos'][0]['type'], "goods_type_alert")

        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l17_goods_type_ai_quota(self):
        """
        [L17] goods_type_ai_quota 查询
        """
        try:
            params = {"goodsType": "goods_type_ai_quota"}
            response = api_instance.send(endpoint_path="goods", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_equal(rep['goodsInfos'][0]['type'], "goods_type_ai_quota")

        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l18_pay_all(self):
        """
        [L18] 创建订单（Checkout Session）并支付,两种不同状态的摄像头 批量购买
        """
        obj_cameras = [self.camera_free, self.camera_none]
        if not all(obj_cameras):
            pytest.skip("缺少 free / none 任意一种摄像头，跳过测试")
        try:
            units_1_40 = DataUtils.get_selected_config(self.goods_data, storage_str="40 GB")
            units_5_60 = DataUtils.get_selected_config(self.goods_data, year_str="5 yr", storage_str="60 GB")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_cameras[0]["id"],
                        "goodsId": 1,
                        "units": units_1_40
                    },
                    {
                        "targetId": obj_cameras[1]["id"],
                        "goodsId": 1,
                        "units": units_5_60
                    }
                ],
                "targetType": "target_camera",
            }

            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)

            # 总价断言
            Assertions.assert_check_order_total_list(obj_cameras, data, rep, self.goods_data)

            order_payload = DataUtils.generate_order_payload(data, rep)
            ss =  StripePaymentService(order_payload)
            payment_result = ss.pay()
            Assertions.assert_true(payment_result, "pay failed")

            dealer_data = refresh_camera_dealer_data(return_cameras_only=False)
            Assertions.assert_cameras_license_active(dealer_data.get('cameras', []), [obj_cameras[0]["id"],
                              obj_cameras[1]["id"]])

            order_rep = ss.get_order_details()
            expected_order_data = {
                "id": ss.local_order_id,
                "status": "confirmed",
                "amount": rep["chargeAmount"],
                "refundAmount": rep["chargeAmount"],
                "items_count": 2
            }

            Assertions.assert_order_details(order_rep, expected_order_data)

            api_instance.terminate_license(target_id_list=[obj_cameras[0]["id"]])
            ss.revoke_or_cancel_order()

            org_id = dealer_data['customers'].get("customer", {}).get("user", {}).get("organization", {}).get("id")
            site_id = dealer_data['sites'].get("id")
            api_instance.login("admin")
            free_json = api_instance.apply_free_license(camera_ids=[obj_cameras[0]["id"]], org_id=org_id,
                                                        site_ids=[site_id])
            Assertions.assert_true(obj_cameras[0]["id"] in free_json.get("successCameraIds", []),
                                   f"成功摄像头列表中未包含预期的 {obj_cameras[0]["id"]}")
            api_instance.login("dealer")


        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l19_orders_cancel(self):
        """
        [L19] 下订单后未付款，取消订单 order_orders_id_cancel
        """
        try:
            if not self.camera_none:
                pytest.skip("未找到 none 摄像头，跳过测试")

            obj_camera = self.camera_none

            units = DataUtils.get_selected_config(self.goods_data, year_str="5 yr")
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }
            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            order_payload = DataUtils.generate_order_payload(data, rep)
            ss = StripePaymentService(order_payload)
            cs_id = ss.create_order_and_get_session_id()
            ss.revoke_or_cancel_order(is_paid_and_refund=False)

            order_rep = ss.get_order_details()
            expected_order_data = {
                "id": ss.local_order_id,
                "status": "cancelled",
                "amount": rep["chargeAmount"],
                "refundAmount": str(rep["chargeAmount"]),
                "items_count": 1,
                "isRefunded": False,

            }
            Assertions.assert_order_details(order_rep, expected_order_data)


        except AssertionError:
            raise  # 断言失败直接抛
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    @pytest.mark.P0
    @pytest.mark.pay
    def test_l20_query_order_list(self):
        """
        [L20] 查询所有订单
        """
        try:
            params = {
                "paging.limit": 20,
                "paging.offset": 0,
            }
            response = api_instance.send(endpoint_path="order_orders", method="GET", params=params, is_valid=True)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            Assertions.assert_order_list_fields_exist(rep)

        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise


    @pytest.mark.P0
    @pytest.mark.pay
    def test_l21_pay_expired(self):
        """
        [l21] 支付超时
        Returns:

        """
        try:
            if not self.camera_none:
                pytest.skip("未找到 none 摄像头，跳过测试")
            obj_camera = self.camera_none
            units = DataUtils.get_selected_config(self.goods_data, year_str="3 yr", storage_str="60 GB",
                                                  monitoring_enabled=True)
            data = {
                "choosedUnits": [
                    {
                        "targetId": obj_camera["id"],
                        "goodsId": 1,
                        "units": units
                    }
                ],
                "targetType": "target_camera",
            }
            response = api_instance.send(endpoint_path="license_price", method="POST", data=data)
            Assertions.assert_status_code(response, 200)
            rep = json.loads(response.content)
            order_payload = DataUtils.generate_order_payload(data, rep)
            ss = StripePaymentService(order_payload)
            Assertions.assert_true(ss.pay_expired())
            order_rep = ss.get_order_details()
            expected_order_data = {
                "id": ss.local_order_id,
                "status": "expired",
                "amount": rep["chargeAmount"],
                "items_count": 1,
                "isRefunded": False,

            }
            Assertions.assert_order_details(order_rep, expected_order_data)


        except AssertionError:
            raise
        except Exception as e:
            print(f"Unexpected error:{e}")
            raise
