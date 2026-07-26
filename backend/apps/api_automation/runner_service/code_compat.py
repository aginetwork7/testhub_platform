from __future__ import annotations

import json
import os
import random
import statistics
import time
import uuid
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests


MODEL_RESULT_DIR = os.environ.get('TESTHUB_MODEL_RESULT_DIR', '/artifacts/model-results')
TEST_ASSET_DATA_DIR = Path(__file__).resolve().parent / 'test_assets' / 'data' / 'database'
HTTP_RESPONSE_SCHEMA_FILE = Path(__file__).resolve().parent / 'test_assets' / 'config' / 'schemas' / 'http_response_schemas.json'
_http_response_schemas: dict[str, Any] | None = None


class RequestError(RuntimeError):
    pass


class PasswordEncryptor:
    def encrypt_stage(self, password: str, username: str, stage: str = 'network') -> str:
        if stage != 'network':
            raise ValueError(f'不支持的密码加密阶段: {stage}')
        return _network_password(username, password, _SPECIFICATION['configuration'], {})


class _Faker:
    _ALERT_TAGS = (
        'other', 'loitering', 'brawling', 'trespassing', 'theft', 'firearm', 'arson', 'injury',
        'illegal_dumping', 'dumpster_diving', 'encampment', 'vandalism', 'break_in', 'drug_use',
    )

    def generate_uuid(self) -> str:
        return str(uuid.uuid4())

    def generate_name(self) -> str:
        return f'test-{uuid.uuid4().hex[:10]}'

    def generate_address(self) -> str:
        return f'{random.randint(100, 9999)} Test Avenue'

    def generate_city(self) -> str:
        return 'Las Vegas'

    def generate_state(self) -> str:
        return 'NV'

    def generate_zipcode(self) -> str:
        return f'{random.randint(10000, 99999)}'

    def generate_latitude(self) -> str:
        return '36'

    def generate_longitude(self) -> str:
        return '-115'

    def generate_email(self) -> str:
        return f'test-{uuid.uuid4().hex[:10]}@example.test'

    def generate_phone_number(self) -> str:
        return f'+1702{random.randint(2000000, 9999999)}'

    def generate_license_plate(self) -> str:
        return f'TEST{random.randint(1000, 9999)}'

    def generate_timezone(self) -> str:
        return 'Asia/Shanghai'

    def generate_alert_tag(self) -> str:
        return random.choice(self._ALERT_TAGS)

    def generate_timestamps_in_period(self, unit: str = 'day', precision: str = 'ms') -> tuple[int, int]:
        now = time.time()
        if unit == 'day':
            start = int(now // 86400 * 86400)
            end = start + 86399
        else:
            start = int(now)
            end = start
        return (start * 1000, end * 1000) if precision == 'ms' else (start, end)


faker = _Faker()


class _Logger:
    def debug(self, *_: Any, **__: Any) -> None:
        return None

    info = debug
    warning = debug
    error = debug


class _Config:
    def get(self, path: str, default: Any = None) -> Any:
        current: Any = _SPECIFICATION.get('configuration', {}).get('runtime_settings', {})
        for key in path.split('.'):
            if not isinstance(current, dict):
                return default
            current = current.get(key)
            if current is None:
                return default
        return current


logger = _Logger()


class Assertions:
    @staticmethod
    def assert_status_code(response: requests.Response, expected: int) -> None:
        assert response.status_code == expected, f'状态码期望 {expected}，实际 {response.status_code}'

    @staticmethod
    def assert_equal(actual: Any, expected: Any) -> None:
        assert actual == expected, f'断言失败: {actual!r} != {expected!r}'

    @staticmethod
    def assert_not_equal(actual: Any, expected: Any) -> None:
        assert actual != expected, f'断言失败: {actual!r} == {expected!r}'

    @staticmethod
    def assert_true(condition: Any, error_message: str | None = None) -> None:
        assert condition, error_message or '断言条件不成立。'

    @staticmethod
    def assert_false(condition: Any) -> None:
        assert not condition, '断言条件应为假。'

    @staticmethod
    def assert_empty(value: Any) -> None:
        assert not value, f'期望为空，实际为 {value!r}'

    @staticmethod
    def assert_not_empty(value: Any) -> None:
        assert value, '期望非空。'

    @staticmethod
    def assert_in(value: Any, collection: Any) -> None:
        assert value in collection, f'{value!r} 不在目标集合中。'

    @staticmethod
    def assert_not_in(value: Any, collection: Any) -> None:
        assert value not in collection, f'{value!r} 在目标集合中。'

    @staticmethod
    def assert_equal_sorted(actual: list[Any], expected: list[Any]) -> None:
        assert sorted(actual) == sorted(expected), f'无序列表断言失败: {actual!r} != {expected!r}'

    @staticmethod
    def assert_startswith(actual: str, expected_prefix: str) -> None:
        assert actual.startswith(expected_prefix), f'{actual!r} 不以 {expected_prefix!r} 开头。'

    @staticmethod
    def assert_is_instance(value: Any, expected_type: type) -> None:
        assert isinstance(value, expected_type), f'{value!r} 不是 {expected_type!r} 实例。'

    @staticmethod
    def assert_raises(exception_type: type[BaseException], function: Any, *args: Any, **kwargs: Any) -> None:
        try:
            function(*args, **kwargs)
        except exception_type:
            return
        raise AssertionError(f'预期抛出 {exception_type.__name__}。')

    @staticmethod
    def assert_deep_equal_unordered(expected: Any, actual: Any) -> None:
        def compare(left: Any, right: Any) -> bool:
            if isinstance(left, dict) and isinstance(right, dict):
                return left.keys() == right.keys() and all(compare(left[key], right[key]) for key in left)
            if isinstance(left, list) and isinstance(right, list):
                if len(left) != len(right):
                    return False
                unmatched = list(right)
                for item in left:
                    for index, candidate in enumerate(unmatched):
                        if compare(item, candidate):
                            unmatched.pop(index)
                            break
                    else:
                        return False
                return True
            return left == right

        assert compare(expected, actual), f'深度无序断言失败: {expected!r} != {actual!r}'

    @staticmethod
    def assert_contains_key(data: Any, json_path: str, expected_key: str) -> None:
        value = _simple_json_path(data, json_path)
        assert isinstance(value, dict) and expected_key in value, f'路径 {json_path} 不包含键 {expected_key}。'

    @staticmethod
    def assert_contains_key_in_list(data: Any, json_path: str, expected_key: str) -> None:
        values = _simple_json_path(data, json_path)
        if isinstance(values, dict):
            values = [values]
        assert isinstance(values, list), f'路径 {json_path} 未返回列表。'
        assert any(isinstance(value, dict) and expected_key in value for value in values), (
            f'路径 {json_path} 未包含键 {expected_key}。'
        )

    @staticmethod
    def assert_json(
        expected: dict[str, Any],
        actual: dict[str, Any],
        contain: set[str] | None = None,
        reg: set[str] | None = None,
    ) -> None:
        contain = contain or set()
        reg = reg or set()
        for key, value in expected.items():
            if key not in actual:
                continue
            if key in contain:
                continue
            if key in reg:
                if not re.match(str(actual[key]), str(value)):
                    logger.warning('字段 %s 未匹配正则表达式。', key)
                continue
            if isinstance(value, dict) and isinstance(actual[key], dict):
                Assertions.assert_json(value, actual[key], contain=contain, reg=reg)
            elif isinstance(value, list) and isinstance(actual[key], list):
                for expected_item, actual_item in zip(value, actual[key], strict=False):
                    if isinstance(expected_item, dict) and isinstance(actual_item, dict):
                        Assertions.assert_json(expected_item, actual_item, contain=contain, reg=reg)

    @staticmethod
    def assert_has_value(data: Any, json_path: str, expected_value: Any) -> None:
        value = _simple_json_path(data, json_path)
        values = value if isinstance(value, list) else [value]
        assert expected_value in values, f'路径 {json_path} 未包含值 {expected_value!r}。'

    @staticmethod
    def assert_json_contains(response: requests.Response, expected: dict[str, Any]) -> None:
        data = response.json()
        for key, value in expected.items():
            assert data.get(key) == value, f'JSON 字段 {key} 不匹配。'


class DataUtils:
    @staticmethod
    def merge_dicts(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(first)
        for key, value in second.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = DataUtils.merge_dicts(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    @staticmethod
    def find_item_by_key(
        data: Any,
        key: str,
        value: Any,
        path: str | None = None,
        return_parent: bool = False,
    ) -> Any:
        def find_at_path(item: Any) -> Any:
            current = item
            parent = None
            for part in (path or '').split('.'):
                if isinstance(current, dict) and part in current:
                    parent, current = current, current[part]
                elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                    parent, current = current, current[int(part)]
                else:
                    return None
            if isinstance(current, dict) and current.get(key) == value:
                return parent if return_parent else current
            if isinstance(current, list):
                for child in current:
                    if isinstance(child, dict) and child.get(key) == value:
                        return current if return_parent else child
            return None

        def visit(item: Any, parent: Any = None, list_parent: Any = None) -> Any:
            if path:
                return find_at_path(item)
            if isinstance(item, list):
                for child in item:
                    found = visit(child, item, child if parent is None else list_parent)
                    if found is not None:
                        return found
            elif isinstance(item, dict):
                if item.get(key) == value:
                    return list_parent if return_parent and list_parent is not None else (parent if return_parent else item)
                for child in item.values():
                    found = visit(child, item, list_parent)
                    if found is not None:
                        return found
            return None

        return visit(data)

    @staticmethod
    def get_selected_config(
        raw_data: dict[str, Any],
        year_str: str = '1 yr',
        storage_str: str = '20 GB',
        monitoring_enabled: bool = False,
        product_type: str = 'goods_type_alert',
    ) -> list[dict[str, Any]]:
        product = next((item for item in raw_data.get('goodsInfos', []) if item.get('type') == product_type), None)
        if not product:
            return []
        units = product.get('goodsUnits', {})
        selected: list[dict[str, Any]] = []

        def add(unit_type: str, unit: dict[str, Any] | None) -> None:
            if unit:
                selected.append({'unitType': unit_type, 'unitId': unit.get('goodsUnitId'), 'unitVersion': unit.get('version')})

        def named(unit_type: str, name: str) -> dict[str, Any] | None:
            return next((item for item in units.get(unit_type, {}).get('units', []) if item.get('name') == name), None)

        add('goods_unit_type_valid_period', named('goods_unit_type_valid_period', year_str))
        add('goods_unit_type_alert_storage', named('goods_unit_type_alert_storage', storage_str))
        algorithms = units.get('goods_unit_type_ai_algorithm', {}).get('units', [])
        add('goods_unit_type_ai_algorithm', algorithms[0] if algorithms else None)
        if monitoring_enabled:
            monitoring = units.get('goods_unit_type_monitoring', {}).get('units', [])
            add('goods_unit_type_monitoring', monitoring[0] if monitoring else None)
        return selected

    @staticmethod
    def generate_order_payload(choosed_units_payload: dict[str, Any], target_info_payload: dict[str, Any]) -> dict[str, Any]:
        amount = target_info_payload.get('chargeAmount')
        currency = target_info_payload.get('currency')
        if amount is None or currency is None:
            raise ValueError("Target Info Payload 缺失 'chargeAmount' 或 'currency' 字段。")
        data = []
        for selection in choosed_units_payload.get('choosedUnits', []):
            update_info = {
                'goodsVersion': 2,
                'units': [
                    {'unitId': item.get('unitId'), 'unitType': item.get('unitType'), 'unitVersion': item.get('unitVersion')}
                    for item in selection.get('units', [])
                ],
            }
            if selection.get('goodsId') is not None:
                update_info['goodsId'] = selection['goodsId']
            data.append({'cameraId': selection.get('targetId'), 'updateInfo': update_info})
        return {'data': data, 'price': {'amount': amount, 'currency': currency}}


class ApiClient:
    def __init__(self, specification: dict[str, Any]) -> None:
        self.configuration = specification['configuration']
        self.session = requests.Session()
        self.default_headers: dict[str, str] = {}
        self.current_auth_info = None
        self._goods_data: dict[str, Any] | None = None
        self._dealer_data: dict[str, Any] | None = None
        self.default_role = self.configuration.get('default_role', 'dealer')

    def login(self, role: str) -> None:
        profile = self.configuration.get('auth_profiles', {}).get(role.lower(), {})
        username = _resolve(profile.get('username'), self.configuration)
        password = _resolve(profile.get('password'), self.configuration)
        if not profile or not username or not password:
            raise RequestError(f'认证角色未配置: {role}')
        password = _network_password(str(username), str(password), self.configuration, profile)
        url = _url(profile.get('login_path', '/auth/login'), self.configuration)
        response = self.session.post(
            url,
            json={profile.get('username_field', 'email'): username, profile.get('password_field', 'password'): password},
            timeout=self.configuration.get('timeout_seconds', 30),
        )
        response.raise_for_status()
        data = response.json()
        token = _nested(data, profile.get('token_path', 'token'))
        if not token:
            raise RequestError(f'认证响应缺少 token: {role}')
        token_prefix = profile.get('token_prefix', '') if profile.get('apply_token_prefix', False) else ''
        self.default_headers[profile.get('authorization_header', 'Authorization')] = f"{token_prefix}{token}"
        org_id = _nested(data, profile.get('organization_path', 'user.organization.id'))
        if org_id is not None:
            self.default_headers[profile.get('organization_header', 'x-org-id')] = str(org_id)
        self.current_auth_info = type(
            'AuthInfo',
            (),
            {
                'token': token,
                'org_id': str(org_id) if org_id is not None else '',
                'username': str(username),
                'password': str(profile.get('password', '')),
            },
        )()

    def get_token(self) -> str | None:
        return self.current_auth_info.token if self.current_auth_info else None

    def get_org_id(self) -> str | None:
        return self.current_auth_info.org_id if self.current_auth_info else None

    @property
    def goods_data(self) -> dict[str, Any]:
        if self._goods_data is None:
            self._goods_data = self._load_context_data('goods_endpoint')
        return self._goods_data

    @property
    def dealer_data(self) -> dict[str, Any]:
        if self._dealer_data is None:
            self._dealer_data = self._load_context_data('dealer_context_endpoint')
        return self._dealer_data

    def clear_dealer_data_cache(self) -> None:
        self._dealer_data = None

    def set_default_header(self, name: str, value: str) -> None:
        self.default_headers[name] = value

    def _load_cache(self, *_: Any, **__: Any) -> dict[str, Any]:
        return {}

    def get_goods_data(self) -> dict[str, Any]:
        return self.goods_data

    def get_dealer_data(self) -> dict[str, Any]:
        return self.dealer_data

    def presign_image(self, record_type: str) -> tuple[str, str, str]:
        response = self.send(
            endpoint_path='s3_temp_object',
            method='POST',
            data={'filename': f'{record_type}.jpeg'},
        )
        response.raise_for_status()
        payload = response.json()
        try:
            return payload['downloadSignUrl'], payload['key'], payload['uploadSignUrl']
        except KeyError as error:
            raise RequestError(f'预签名响应缺少字段: {error}') from error

    def upload_image(self, record_type: str, upload_sign_url: str, data_path: str | Path | None = None) -> None:
        image_path = Path(data_path) / f'{record_type}.jpeg' if data_path else TEST_ASSET_DATA_DIR / f'{record_type}.jpeg'
        if not image_path.is_file():
            raise RequestError(f'测试图像不存在: {image_path}')
        with image_path.open('rb') as image_file:
            response = self.session.put(
                upload_sign_url,
                data=image_file,
                timeout=self.configuration.get('timeout_seconds', 30),
            )
        response.raise_for_status()

    def yolo_detect(self, record_type: str, download_sign_url: str, limit: int = 1) -> list[dict[str, Any]]:
        endpoint = {
            'human': 'asset_tracking_face_recon',
            'car': 'asset_tracking_detect_plate',
        }.get(record_type)
        if endpoint is None:
            raise RequestError(f'不支持的记录类型: {record_type}')
        response = self.send(
            endpoint_path=endpoint,
            method='POST',
            data={'imgUrl': download_sign_url, 'limit': limit},
        )
        response.raise_for_status()
        results = response.json().get('results', [])
        if not results:
            raise RequestError(f'YOLO 检测未返回 {record_type} 结果。')
        if not isinstance(results, list):
            raise RequestError('YOLO 检测响应 results 格式无效。')
        return results

    def prepare_data_for_record(
        self,
        record_type: str,
        data_cache: dict[str, tuple[str, list[dict[str, Any]]]] | None = None,
        enable_local_cache: bool | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        cache = data_cache if data_cache is not None else {}
        if enable_local_cache is None:
            runtime_settings = self.configuration.get('runtime_settings', {})
            enable_local_cache = bool(runtime_settings.get('api', {}).get('database', {}).get('enable_local_cache', False))
        if enable_local_cache and record_type in cache:
            return cache[record_type]
        download_sign_url, s3_key, upload_sign_url = self.presign_image(record_type)
        self.upload_image(record_type, upload_sign_url)
        results = self.yolo_detect(record_type, download_sign_url)
        if record_type == 'car':
            results[0]['url'] = download_sign_url
        prepared_data = (s3_key, results)
        if enable_local_cache:
            cache[record_type] = prepared_data
        return prepared_data

    def send(self, endpoint_path: str | None = None, method: str = 'GET', **kwargs: Any) -> requests.Response:
        endpoint_template = self.configuration.get('endpoint_paths', {}).get(endpoint_path, endpoint_path or '')
        try:
            endpoint = str(endpoint_template).format(**kwargs)
        except KeyError as error:
            raise RequestError(f'接口路径缺少参数: {error}') from error
        if not endpoint:
            raise RequestError(f'未找到接口别名: {endpoint_path}')
        request_data = kwargs.get('data') if method.upper() in {'POST', 'PUT', 'PATCH'} else None
        if endpoint_path == 'case_cases_caseId_medias' and isinstance(request_data, dict):
            request_data = deepcopy(request_data)
            for media in request_data.get('medias', []):
                if isinstance(media, dict) and not media.get('name'):
                    media['name'] = Path(str(media.get('key', 'test-image'))).name[:50] or 'test-image'
        response = self.session.request(
            method=method.upper(),
            url=_url(endpoint, self.configuration),
            params=kwargs.get('params'),
            json=request_data,
            headers={**self.default_headers, **(kwargs.get('headers') or {})},
            timeout=self.configuration.get('timeout_seconds', 30),
        )
        if endpoint_path == 'case_cases_merge_into' and response.ok:
            time.sleep(2)
        _validate_http_response_schema(response, method, str(endpoint_template), self.configuration)
        return response

    def get(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.send(endpoint, 'GET', **kwargs)

    def post(self, endpoint: str, data: Any = None, **kwargs: Any) -> requests.Response:
        return self.send(endpoint, 'POST', data=data, **kwargs)

    def put(self, endpoint: str, data: Any = None, **kwargs: Any) -> requests.Response:
        return self.send(endpoint, 'PUT', data=data, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.send(endpoint, 'DELETE', **kwargs)

    def _load_context_data(self, endpoint_config_key: str) -> dict[str, Any]:
        data_endpoints = self.configuration.get('data_endpoints', {})
        endpoint = data_endpoints.get(endpoint_config_key)
        if endpoint_config_key == 'dealer_context_endpoint' and not endpoint:
            return self._load_dealer_context()
        if not endpoint:
            raise RequestError(f'运行配置缺少数据端点: {endpoint_config_key}')
        response = self.send(endpoint_path=endpoint, method='GET')
        response.raise_for_status()
        payload = response.json()
        return payload.get('data', payload)

    def _load_dealer_context(self) -> dict[str, Any]:
        original_headers = dict(self.default_headers)
        try:
            self.login('dealer')
            context: dict[str, Any] = {
                'dealer': {'email': self.current_auth_info.username if self.current_auth_info else ''},
            }
            customer_name = self.configuration.get('auth_profiles', {}).get('customer', {}).get('username', '')
            customers_response = self.send(
                endpoint_path='user_customers',
                method='GET',
                params={'with_dealer_rep': 'true', 'name': customer_name, 'page.limit': 6, 'page.offset': 0},
            )
            customers_response.raise_for_status()
            customers = customers_response.json().get('data', [])
            if not customers:
                raise RequestError('未找到可用于自动化测试的客户数据。')
            context['customers'] = customers[0]
            organization_id = str(
                context['customers'].get('customer', {}).get('user', {}).get('organization', {}).get('id', '')
            )
            if not organization_id:
                raise RequestError('客户数据缺少 organization id。')
            self.default_headers['x-org-id'] = organization_id
            sites_response = self.send(
                endpoint_path='site_tree',
                method='GET',
                params={'withCameraNum': 'true', 'withMonitorInfo': 'true'},
            )
            sites_response.raise_for_status()
            sites = sites_response.json().get('sites', [])
            if not sites:
                raise RequestError('客户组织没有可用站点。')
            context['sites'] = sites[0]
            site_id = context['sites'].get('id')
            nvrs_response = self.send(
                endpoint_path='device_nvrs',
                method='GET',
                params={'siteId': site_id, 'page.limit': 100},
            )
            nvrs_response.raise_for_status()
            nvrs = nvrs_response.json().get('data', [])
            if not nvrs:
                raise RequestError('站点没有可用 NVR。')
            context['nvrs'] = nvrs[0]
            nvr_id = context['nvrs'].get('id')
            cameras_response = self.send(
                endpoint_path='camera_cameras',
                method='GET',
                params={'siteId': site_id, 'nvrId': nvr_id, 'page.limit': 100},
            )
            cameras_response.raise_for_status()
            context['cameras'] = cameras_response.json().get('data', [])
            speakers_response = self.send(
                endpoint_path='speaker_speakers',
                method='GET',
                params={'siteId': site_id, 'nvrId': nvr_id, 'page.limit': 100},
            )
            speakers_response.raise_for_status()
            context['speakers'] = speakers_response.json().get('data', [])
            return context
        finally:
            self.default_headers = original_headers


class StripePaymentService:
    def __init__(self, order_payload: dict[str, Any] | None = None) -> None:
        if not order_payload or 'price' not in order_payload:
            raise ValueError('订单负载缺少 price。')
        self.payload = order_payload
        self.amount = order_payload['price'].get('amount')
        self.currency = order_payload['price'].get('currency')
        self.local_order_id: str | None = None
        self.session_id: str | None = None

    @staticmethod
    def clear_mock_data() -> bool:
        config = _SPECIFICATION['configuration'].get('payment_config', {})
        mock_base_url = _resolve(config.get('mock_base_url') or config.get('base_url'), _SPECIFICATION['configuration'])
        if not mock_base_url:
            return False
        response = requests.post(
            urljoin(f'{mock_base_url.rstrip("/")}/', 'admin/clear'),
            headers=_resolve(config.get('headers', {}), _SPECIFICATION['configuration']),
            timeout=_SPECIFICATION['configuration'].get('timeout_seconds', 30),
        )
        return response.ok and response.json().get('ok') is True

    def create_order_and_get_session_id(self) -> str:
        config = _SPECIFICATION['configuration'].get('payment_config', {})
        api_instance.login(config.get('role', 'dealer'))
        response = api_instance.send(
            endpoint_path=config.get('order_endpoint', 'camera_orders'),
            method='POST',
            data=self.payload,
        )
        response.raise_for_status()


class ModelHandler:
    def __init__(self, session: requests.Session | None = None, timeout: int = 30) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.configuration = _SPECIFICATION['configuration']

    def call_model(self, image_path: str, model_type: str = 'qwen') -> dict[str, Any]:
        profile = self.configuration.get('model_profiles', {}).get(model_type, {})
        if not profile:
            raise RequestError(f'模型服务未配置: {model_type}')
        image_data = self._prepare_image(image_path)
        content = self._build_content(image_data, profile)
        payload = {
            'model': profile.get('model'),
            'temperature': profile.get('temperature', 0),
            'response_format': profile.get('response_format', {'type': 'json_object'}),
            'messages': [{'role': 'user', 'content': content}],
        }
        started = time.monotonic()
        response = self.session.post(
            _resolve(profile.get('url'), self.configuration),
            json=payload,
            headers=_resolve(profile.get('headers', {}), self.configuration),
            timeout=profile.get('timeout_seconds', self.timeout),
        )
        response.raise_for_status()
        result = response.json()
        result['response_time'] = time.monotonic() - started
        return result

    def save_result(self, image_name: str, response: dict[str, Any], result_path: str) -> str:
        destination = _safe_artifact_path(result_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.parse_response(response, image_name)
        with destination.open('a', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False)
            output.write('\n')
        return str(destination)

    def parse_response(self, response: dict[str, Any], image_name: str) -> dict[str, Any]:
        content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {}
        properties = parsed.get('properties', parsed)
        parsed_results = {
            'cars': properties.get('cars', []),
            'people': properties.get('people', []),
            'objects': properties.get('objects', []),
            'natural_language_description': properties.get('natural_language_description', ''),
            'alarm_types': properties.get('alarm_types', []),
        }
        return {
            'image_path': image_name,
            'response_time': response.get('response_time', 0),
            'token_usage': response.get('usage', {}),
            'parsed_results': parsed_results,
            'detection_summary': {
                'car_count': len(parsed_results['cars']),
                'person_count': len(parsed_results['people']),
                'object_count': len(parsed_results['objects']),
                'alarm_count': len(parsed_results['alarm_types']),
            },
            'response': response,
        }

    def call_model_perf(self, image_path: str, num_requests: int = 20, concurrent_requests: int = 10, model_type: str = 'qwen') -> tuple[str, list[dict[str, Any]]]:
        started = time.monotonic()
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
            futures = [executor.submit(self.call_model, image_path, model_type) for _ in range(num_requests)]
            for future in as_completed(futures):
                try:
                    response = future.result()
                    results.append({'success': True, 'response_time': response.get('response_time', 0), 'response': response})
                except Exception as error:
                    results.append({'success': False, 'error': str(error)})
        report_path = _safe_artifact_path(f'model-results/{model_type}-performance-{uuid.uuid4().hex}.json')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        successful = [item for item in results if item['success']]
        report_path.write_text(json.dumps({
            'requests': num_requests,
            'concurrency': concurrent_requests,
            'duration_seconds': time.monotonic() - started,
            'successful': len(successful),
            'failed': len(results) - len(successful),
            'average_response_time': statistics.mean([item['response_time'] for item in successful]) if successful else 0,
            'results': results,
        }, ensure_ascii=False), encoding='utf-8')
        return str(report_path), results

    def _prepare_image(self, image_path: str) -> str:
        image_mapping = self.configuration.get('model_images', {})
        source = image_mapping.get(image_path, image_path)
        if source.startswith(('data:image/', 'http://', 'https://')):
            return source
        source_path = _safe_artifact_path(source)
        if not source_path.is_file():
            raise RequestError(f'模型图片不存在: {image_path}')
        from PIL import Image
        from io import BytesIO
        import base64

        with Image.open(source_path) as image:
            converted = image.convert('RGB')
            buffer = BytesIO()
            converted.save(buffer, format='JPEG')
        return f'data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}'

    def _build_content(self, image_data: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
        prompt = profile.get('prompt', '')
        schema = profile.get('schema', '')
        natural_language = profile.get('natural_language', '')
        content = [
            {'type': 'text', 'text': f'{prompt}\n{schema}'.strip()},
            {'type': 'image_url', 'image_url': {'url': image_data}},
        ]
        if natural_language:
            content.append({'type': 'text', 'text': natural_language})
        return content
        response_data = response.json()
        self.local_order_id = str(response_data.get('orderId') or '')
        redirect_url = response_data.get('redirectUrl', '')
        parsed_url = urlparse(redirect_url)
        self.session_id = parse_qs(parsed_url.query).get('session_id', [None])[0] or parsed_url.path.rsplit('/', 1)[-1]
        if not self.local_order_id or not self.session_id:
            raise RequestError('业务下单响应缺少 orderId 或 Stripe session_id。')
        return self.session_id

    def pay(self) -> bool:
        try:
            self.create_order_and_get_session_id()
            self._override_session('complete', 'paid')
            self._trigger_callback('success')
            return True
        except (RequestError, requests.RequestException, ValueError):
            return False

    def pay_expired(self) -> bool:
        try:
            self.create_order_and_get_session_id()
            self._override_session('expired', 'unpaid')
            self._trigger_callback('expired')
            return True
        except (RequestError, requests.RequestException, ValueError):
            return False

    def revoke_or_cancel_order(self, old_order_id: str | None = None, is_paid_and_refund: bool = True) -> dict[str, Any]:
        config = _SPECIFICATION['configuration'].get('payment_config', {})
        api_instance.login(config.get('role', 'dealer'))
        order_id = old_order_id or self.local_order_id
        if not order_id:
            raise ValueError('缺少订单 ID。')
        endpoint = config.get(
            'revoke_endpoint' if is_paid_and_refund else 'cancel_endpoint',
            'order_orders_id_revoke' if is_paid_and_refund else 'order_orders_id_cancel',
        )
        response = api_instance.send(endpoint_path=endpoint, method='POST', id=order_id)
        response.raise_for_status()
        return response.json()

    def _override_session(self, status: str, payment_status: str) -> None:
        config = _SPECIFICATION['configuration'].get('payment_config', {})
        mock_base_url = _resolve(config.get('mock_base_url') or config.get('base_url'), _SPECIFICATION['configuration'])
        if not mock_base_url or not self.session_id:
            raise RequestError('支付 Mock 服务或 session_id 未配置。')
        response = requests.post(
            urljoin(f'{mock_base_url.rstrip("/")}/', 'admin/override'),
            json={
                'type': 'checkout.session',
                'id': self.session_id,
                'payload': {'status': status, 'payment_status': payment_status, 'client_reference_id': self.local_order_id},
            },
            headers=_resolve(config.get('headers', {}), _SPECIFICATION['configuration']),
            timeout=_SPECIFICATION['configuration'].get('timeout_seconds', 30),
        )
        response.raise_for_status()

    def _trigger_callback(self, event_type: str) -> None:
        config = _SPECIFICATION['configuration'].get('payment_config', {})
        callback_url = _resolve(config.get(f'{event_type}_callback_url'), _SPECIFICATION['configuration'])
        if not callback_url:
            raise RequestError(f'支付 {event_type} 回调地址未配置。')
        response = requests.post(
            callback_url,
            json={'session_id': self.session_id, 'order_id': self.local_order_id, 'event_type': event_type},
            headers=_resolve(config.get('callback_headers', {}), _SPECIFICATION['configuration']),
            timeout=_SPECIFICATION['configuration'].get('timeout_seconds', 30),
        )
        response.raise_for_status()


class WebSocketRequest:
    @staticmethod
    def create(data: dict[str, Any], org_id: str | None = None) -> dict[str, Any]:
        action_name = next(iter(data), '')
        action = WEBSOCKET_PARAMS.get('action', {}).get(action_name, action_name)
        return {
            'request': {
                'id': faker.generate_uuid(),
                'act': action,
                'data': data,
            },
            'headers': {'org_id': org_id or api_instance.get_org_id()},
        }


class WebSocketClient:
    async def send_request(
        self,
        data: dict[str, Any],
        validate_response: bool = False,
        timeout: int = 10,
        **_: Any,
    ) -> dict[str, Any]:
        import asyncio
        import websockets

        websocket_url = _resolve(_SPECIFICATION['configuration'].get('websocket_url'), _SPECIFICATION['configuration'])
        if not websocket_url:
            raise RequestError('WebSocket 地址未配置。')
        async with websockets.connect(websocket_url, additional_headers=api_instance.default_headers) as connection:
            await connection.send(json.dumps(data))
            response = json.loads(await asyncio.wait_for(connection.recv(), timeout))
        if validate_response:
            _validate_websocket_response(data, response)
        return response

    async def close(self) -> None:
        return None


async def create_websocket_client() -> WebSocketClient:
    return WebSocketClient()


_SPECIFICATION = json.loads(open(os.environ['TESTHUB_SPEC_PATH'], encoding='utf-8').read())
api_instance = ApiClient(_SPECIFICATION)
WEBSOCKET_PARAMS: dict[str, Any] = _SPECIFICATION['configuration'].get('websocket_params', {})
config = _Config()


def load_api_instance() -> ApiClient:
    return api_instance


def _resolve(value: Any, configuration: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    for key, item in configuration.get('variables', {}).items():
        replacement = item.get('currentValue', item.get('initialValue', '')) if isinstance(item, dict) else item
        value = value.replace(f'{{{{{key}}}}}', str(replacement))
    return value


def _network_password(username: str, password: str, configuration: dict[str, Any], profile: dict[str, Any]) -> str:
    password_mode = profile.get('password_mode', 'argon2_network')
    if password_mode == 'plain':
        return password
    security = configuration.get('runtime_settings', {}).get('security', {}).get('password', {})
    fixed_salt = security.get('fixed_salt') or configuration.get('variables', {}).get('SALT')
    if not fixed_salt:
        raise RequestError('认证配置缺少 SALT，无法执行 Argon2 密码转换。')
    try:
        from argon2.low_level import Type, hash_secret_raw
    except ImportError as error:
        raise RequestError('Runner 缺少 argon2-cffi 依赖。') from error
    parameters = security.get('argon2', {})
    first = parameters.get('first_stage', {})
    second = parameters.get('second_stage', {})
    password_salt = hash_secret_raw(
        secret=username.encode('ascii'),
        salt=str(fixed_salt).encode('ascii'),
        time_cost=first.get('time_cost', 1),
        memory_cost=first.get('memory_cost', 46) * 1024,
        parallelism=first.get('parallelism', 1),
        hash_len=first.get('hash_len', 16),
        type=Type.ID,
        version=19,
    ).hex()
    return hash_secret_raw(
        secret=password.encode('ascii'),
        salt=password_salt.encode('ascii'),
        time_cost=second.get('time_cost', 1),
        memory_cost=second.get('memory_cost', 46) * 1024,
        parallelism=second.get('parallelism', 1),
        hash_len=second.get('hash_len', 32),
        type=Type.ID,
        version=19,
    ).hex()


def _url(endpoint: str, configuration: dict[str, Any]) -> str:
    if endpoint.startswith(('http://', 'https://')):
        return endpoint
    return urljoin(f"{configuration.get('base_url', '').rstrip('/')}/", endpoint.lstrip('/'))


def _nested(data: Any, path: str) -> Any:
    current = data
    for key in path.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _safe_artifact_path(relative_path: str) -> Path:
    root = Path(MODEL_RESULT_DIR).resolve()
    candidate = (root / relative_path).resolve() if not os.path.isabs(relative_path) else Path(relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise RequestError('模型文件路径不在受控产物目录内。')
    return candidate


if _SPECIFICATION['configuration'].get('auto_login_default_role', True):
    api_instance.login(api_instance.default_role)


def _simple_json_path(data: Any, json_path: str) -> Any:
    # Keep leading wildcard selectors valid, e.g. "[*].id".
    path = json_path.strip().lstrip('$').lstrip('.').replace('[*]', '.[*]').lstrip('.')
    if not path:
        return data
    current = data
    for part in path.split('.'):
        if part == '[*]':
            if not isinstance(current, list):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)] if int(part) < len(current) else None
        elif isinstance(current, list):
            current = [item.get(part) for item in current if isinstance(item, dict) and part in item]
        else:
            return None
    return current


def _validate_http_response_schema(
    response: requests.Response,
    method: str,
    endpoint_template: str,
    configuration: dict[str, Any],
) -> None:
    validation = configuration.get('runtime_settings', {}).get('test', {}).get('validation', {})
    if not validation.get('http_schema_enabled', False):
        return
    schema = _get_http_response_schema(method, endpoint_template, response.status_code)
    if schema is None:
        return
    try:
        payload = response.json()
    except ValueError as error:
        raise AssertionError(f'HTTP Schema 校验需要 JSON 响应: {error}') from error
    from jsonschema import Draft7Validator

    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        path = '.'.join(str(part) for part in error.path) or '$'
        raise AssertionError(f'HTTP Schema 校验失败 [{method.upper()} {endpoint_template} {response.status_code}]: {path}: {error.message}')


def _get_http_response_schema(method: str, endpoint_template: str, status_code: int) -> dict[str, Any] | None:
    global _http_response_schemas
    if _http_response_schemas is None:
        try:
            document = json.loads(HTTP_RESPONSE_SCHEMA_FILE.read_text(encoding='utf-8'))
            _http_response_schemas = document.get('schemas', {}) if isinstance(document, dict) else {}
        except (OSError, json.JSONDecodeError):
            _http_response_schemas = {}
    key = f'{method.upper()} {endpoint_template} {status_code}'
    return _http_response_schemas.get(key) or _http_response_schemas.get(f'{method.upper()} {endpoint_template} default')


def _validate_websocket_response(request_data: dict[str, Any], response_data: dict[str, Any]) -> None:
    error = response_data.get('result', {}).get('error')
    if error:
        raise AssertionError(f'WebSocket 返回错误: {error}')
    action = request_data.get('request', {}).get('act', '')
    schema = _SPECIFICATION['configuration'].get('websocket_schemas', {}).get(action)
    if not schema:
        return
    from jsonschema import Draft7Validator

    errors = sorted(Draft7Validator(schema).iter_errors(response_data), key=lambda item: item.path)
    if errors:
        raise AssertionError(f'WebSocket Schema 校验失败: {errors[0].message}')