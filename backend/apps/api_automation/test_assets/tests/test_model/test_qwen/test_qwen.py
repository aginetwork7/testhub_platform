import json
import os
import time
import glob
import pytest
import requests
from src.core.api_exceptions import RequestError
from src.core.logger import logger
from src.utils.assertions import Assertions
from src.utils.data_utils import DATA_DIR, MODEL_RESULT_DIR
from src.utils.model_handler import ModelHandler


class TestQwenModel:
    @classmethod
    def setup_class(cls):
        """测试类初始化"""
        cls.test_images_dir = os.path.join(DATA_DIR, "qwen")
        if not os.path.exists(cls.test_images_dir):
            os.makedirs(cls.test_images_dir)
        cls.session = requests.Session()
        cls.model_handler = ModelHandler(cls.session)
        print("\nSetting up TestQwenModel class...")

    @classmethod
    def get_latest_result_file(cls, file_pattern):
        """获取最新的结果文件"""
        files = glob.glob(os.path.join(MODEL_RESULT_DIR, file_pattern))
        if not files:
            return None
        
        # 从文件名中提取时间戳并排序
        def get_timestamp(filename):
            # 提取文件名中的时间戳部分 (格式: YYYYMMDD_HHMMSS)
            import re
            match = re.search(r'(\d{8}_\d{6})', filename)
            return match.group(1) if match else ''
            
        latest_file = max(files, key=get_timestamp)
        logger.info(f"获取到最新结果文件: {os.path.basename(latest_file)}")
        return latest_file

    @classmethod
    def get_image_files(cls):
        """获取测试目录下的所有图片文件"""
        image_files = glob.glob(os.path.join(cls.test_images_dir, "*.jpg")) + \
                     glob.glob(os.path.join(cls.test_images_dir, "*.jpeg")) + \
                     glob.glob(os.path.join(cls.test_images_dir, "*.png"))
        return image_files

    def _test_single_image(self, image_path, model_type="qwen"):
        """通用的单张图片测试方法"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_name = os.path.basename(image_path)
        result_file = os.path.join(MODEL_RESULT_DIR, f"model_{model_type}_img_gun_{timestamp}.json")
        
        if not os.path.exists(image_path):
            pytest.skip(f"测试图片不存在: {image_path}")
        
        start_time = time.time()
        try:
            response = self.model_handler.call_model(image_path, model_type)
            response['execution_time'] = time.time() - start_time
            self.model_handler.save_result(image_name, response, result_file)
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"调用失败，耗时: {execution_time:.2f}秒")
            raise RequestError(f"调用{model_type}模型失败: {str(e)}")

    def _test_all_images(self, model_type="qwen"):
        """通用的批量图片测试方法"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        result_dir = os.path.join(MODEL_RESULT_DIR, f"model_{model_type}_img_all_{timestamp}.json")
        
        image_files = self.get_image_files()
        if not image_files:
            pytest.skip(f"测试目录下没有图片文件: {self.test_images_dir}")

        with open(result_dir, 'w', encoding='utf-8') as f:
            f.write('[\n')

        failed_images = []
        for image_path in image_files:
            image_name = os.path.basename(image_path)
            start_time = time.time()
            
            try:
                response = self.model_handler.call_model(image_path, model_type)
                response['execution_time'] = time.time() - start_time
                self.model_handler.save_result(image_name, response, result_dir)
                
                if image_path != image_files[-1]:
                    with open(result_dir, 'a+', encoding='utf-8') as f:
                        f.write(',\n')
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"处理图片 {image_name} 失败，耗时: {execution_time:.2f}秒, 错误: {str(e)}")
                failed_images.append({
                    'image': image_name,
                    'error': str(e),
                    'execution_time': execution_time
                })

        with open(result_dir, 'a+', encoding='utf-8') as f:
            f.write('\n]')

        if failed_images:
            fail_message = f"以下图片处理失败:\n" + \
                          "\n".join([f"{item['image']}: {item['error']}" for item in failed_images])
            pytest.fail(fail_message)

    @classmethod
    def _parse_model_result(cls, result, item_key, item_name):
        """解析模型结果的通用方法"""
        if not result:
            return None
            
        parsed = result.get('parsed_results', {})
        if item_key in ['car_count', 'person_count']:
            return result.get('detection_summary', {}).get(item_key, 0)
            
        if item_key in ['cars', 'people']:
            items = parsed.get(item_key, [])
            if isinstance(items, dict) and 'items' in items:
                items = items['items']
            
            if not items or not isinstance(items, list) or len(items) == 0:
                return {}
                
            if item_name == 'license_plates' and item_key == 'cars':
                return [car.get('license_plate', 'Unknown') for car in items]
            
            return {k: v for k, v in items[0].items()}
            
        return parsed.get(item_key, [])

    @classmethod
    def _format_result_value(cls, value):
        """格式化结果值的通用方法"""
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                if 'license_plate' in value[0]:
                    return ', '.join([str(item.get('license_plate', 'Unknown')) for item in value])
                elif 'gender' in value[0]:
                    return ', '.join([
                        f"{item.get('gender', 'unknown')} ({item.get('activity', 'unknown')})"
                        for item in value
                    ])
                return ', '.join([str(item.get('name', str(item))) for item in value])
        elif isinstance(value, dict):
            if 'items' in value:
                return cls._format_result_value(value['items'])
            return str(value)
        return str(value) if value else '无'

    @classmethod
    def compare_model_results(cls):
        """对比两个模型的测试结果"""
        # 获取最新的测试结果文件
        qwen_file = cls.get_latest_result_file("model_qw_img_all_*.json")
        gpt4_file = cls.get_latest_result_file("model_gpt_img_all_*.json")

        if not qwen_file or not gpt4_file:
            logger.warning("找不到测试结果文件")
            return None

        # 读取结果文件
        with open(qwen_file, 'r', encoding='utf-8') as f:
            qwen_results = json.load(f)
        with open(gpt4_file, 'r', encoding='utf-8') as f:
            gpt4_results = json.load(f)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        compare_file = os.path.join(MODEL_RESULT_DIR, f"model_comparison_{timestamp}.md")

        # 定义比较项
        items = [
            ("natural_language_description", "natural_language_description"),
            ("alarm_types", "alarm_types"),
            ("objects", "objects"),
            ("car_count", "car_count"),
            ("person_count", "person_count"),
            ("license_plates", "cars"),
            ("people_item", "people"),
            ("car_item", "cars")
        ]

        with open(compare_file, 'w', encoding='utf-8') as f:
            # 写入表头
            f.write("| 图片名称 | 分析项 | Qwen | GPT4oMINI |\n")
            f.write("|---------|--------|------|------------|\n")

            # 获取所有唯一的图片名称
            image_names = set([r['image_path'] for r in qwen_results + gpt4_results])

            for image_name in sorted(image_names):
                qwen_result = next((r for r in qwen_results if r['image_path'] == image_name), None)
                gpt4_result = next((r for r in gpt4_results if r['image_path'] == image_name), None)

                for i, (item_name, item_key) in enumerate(items):
                    qwen_value = cls._parse_model_result(qwen_result, item_key, item_name)
                    gpt4_value = cls._parse_model_result(gpt4_result, item_key, item_name)

                    qwen_info = cls._format_result_value(qwen_value) if qwen_value is not None else "未找到结果"
                    gpt4_info = cls._format_result_value(gpt4_value) if gpt4_value is not None else "未找到结果"

                    row_image_name = image_name if i == 0 else ""
                    f.write(f"| {row_image_name} | {item_name} | {qwen_info} | {gpt4_info} |\n")

        logger.info(f"对比结果已保存到：{compare_file}")
        return compare_file

    @classmethod
    def teardown_class(cls):
        """在整个测试类结束之后执行的动作"""
        try:
            compare_file = cls.compare_model_results()
            if compare_file:
                logger.info(f"测试完成，模型对比报告已生成：{compare_file}")
        except Exception as e:
            logger.error(f"生成模型对比报告时发生错误: {str(e)}")

    @pytest.mark.model
    def test_model_qw_img_gun(self):
        """测试单张图片调用"""
        image_path = os.path.join(self.test_images_dir, "person_gun.jpeg")
        self._test_single_image(image_path, "qwen")

    @pytest.mark.model
    def test_model_gpt_img_gun(self):
        """测试单张图片调用"""
        image_path = os.path.join(self.test_images_dir, "person_gun.jpeg")
        self._test_single_image(image_path, "gpt")

    @pytest.mark.model
    def test_model_qw_img_all(self):
        """测试目录下所有图片调用"""
        self._test_all_images("qwen")

    @pytest.mark.model
    def test_model_gpt_img_all(self):
        """测试目录下所有图片调用"""
        self._test_all_images("gpt")

    @pytest.mark.model
    def test_model_performance(self):
        """模型性能测试"""
        image_path = os.path.join(self.test_images_dir, "person_gun.jpeg")
        image_path = "img_1"
        num_requests = 5
        concurrent_requests = 2
        model_type="gpt"
        try:
            # 执行性能测试
            report_file, results = self.model_handler.call_model_perf(
                image_path=image_path,
                num_requests=num_requests,
                concurrent_requests=concurrent_requests,
                model_type=model_type
            )
            
            # 处理并保存详细结果
            detailed_results_file = self.model_handler.process_and_save_results(
                all_results=results,
                image_path=image_path,
                num_requests=num_requests,
                concurrent_requests=concurrent_requests,
                model_type=model_type
            )
            
            # 验证测试结果
            assert os.path.exists(report_file), "性能测试报告文件未生成"
            assert os.path.exists(detailed_results_file), "详细结果文件未生成"
            
            # 验证结果内容
            with open(detailed_results_file, 'r', encoding='utf-8') as f:
                detailed_results = json.load(f)
                assert "test_config" in detailed_results, "缺少测试配置信息"
                assert "summary" in detailed_results, "缺少测试结果摘要"
                assert "request_results" in detailed_results, "缺少请求结果详情"
                
                # 验证测试配置
                assert detailed_results["test_config"]["total_requests"] == num_requests
                assert detailed_results["test_config"]["concurrent_requests"] == concurrent_requests
                
                # 验证结果数量
                assert len(detailed_results["request_results"]) == num_requests
                
                # 验证成功率大于0
                assert detailed_results["summary"]["success_rate"] > 0
            
            logger.info(f"性能测试报告已保存到: {report_file}")
            logger.info(f"详细测试结果已保存到: {detailed_results_file}")
            
        except Exception as e:
            logger.error(f"性能测试失败: {str(e)}")
            raise

