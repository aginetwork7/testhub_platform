"""Pure business payload construction tools."""

from __future__ import annotations

from copy import deepcopy
import base64
from pathlib import Path
from time import time
from typing import Any, Literal
from uuid import uuid4

import requests
from PIL import Image
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


AlertType = Literal['person', 'vehicle']


class BusinessTools:
    """Build business payloads without sending requests or uploading media."""

    @staticmethod
    def construct_alert_event(
        alert_type: AlertType = 'person',
        camera_mac: str = '00:00:00:00:00:00',
        camera_name: str = 'Test Camera',
        created_at: int | None = None,
        coat_color: int = 1,
        trousers_color: int = 2,
        vehicle_color: int = 1,
        rule_type: int = 0,
        count: int = 1,
    ) -> dict[str, Any]:
        if alert_type not in {'person', 'vehicle'}:
            return {'success': False, 'error': '事件类型仅支持 person 或 vehicle。'}
        if not camera_mac.strip() or not camera_name.strip():
            return {'success': False, 'error': '摄像头 MAC 和名称不能为空。'}
        if count < 1 or count > 100:
            return {'success': False, 'error': '构造数量必须介于 1 到 100。'}
        if rule_type not in {0, 1, 2, 3}:
            return {'success': False, 'error': '规则类型仅支持 0（入侵检测）至 3（进入区域）。'}

        timestamp = int(created_at if created_at is not None else time())
        events = [
            BusinessTools._build_alert_event(
                alert_type=alert_type,
                camera_mac=camera_mac,
                camera_name=camera_name,
                created_at=timestamp,
                coat_color=coat_color,
                trousers_color=trousers_color,
                vehicle_color=vehicle_color,
                rule_type=rule_type,
            )
            for _ in range(count)
        ]
        return {'success': True, 'result': events[0] if count == 1 else events, 'count': count}

    @staticmethod
    def _build_alert_event(
        alert_type: AlertType,
        camera_mac: str,
        camera_name: str,
        created_at: int,
        coat_color: int,
        trousers_color: int,
        vehicle_color: int,
        rule_type: int,
    ) -> dict[str, Any]:
        event = deepcopy(BusinessTools._template(alert_type))
        structure = event['event']['raw']['struct']['StructureInfo']
        event['event']['meta']['uuid'] = str(uuid4())
        event['event']['meta']['camera']['macAddress'] = camera_mac
        event['event']['raw']['struct']['SrcName'] = camera_name
        event['event']['raw']['alarm']['TimeStamp'] = created_at
        event['event']['raw']['struct']['TimeStamp'] = created_at
        for image in structure['ImageInfoList']:
            image['CaptureTime'] = created_at
        if alert_type == 'person':
            rule_info = structure['ObjInfo']['PersonInfoList'][0]['RuleInfo']
            rule_info['RuleType'] = rule_type
            attributes = structure['ObjInfo']['PersonInfoList'][0]['AttributeInfo']
            attributes['CoatColor'] = coat_color
            attributes['TrousersColor'] = trousers_color
        else:
            rule_info = structure['ObjInfo']['VehicleInfoList'][0]['RuleInfo']
            rule_info['RuleType'] = rule_type
            attributes = structure['ObjInfo']['VehicleInfoList'][0]['VehicleAttributeInfo']
            attributes['Color'] = vehicle_color
        return event

    @staticmethod
    def report_alert_events(
        events: list[dict[str, Any]],
        base_url: str,
        device_id: str,
        device_key: str,
        timeout_seconds: int = 30,
        paths: dict[str, str] | None = None,
        media_groups: list[dict[str, Path | None]] | None = None,
        s3_url: str = '',
    ) -> dict[str, Any]:
        if not device_key:
            return {'success': False, 'error': '真实上报需要一次性设备私钥。'}
        try:
            key_bytes = base64.b64decode(device_key, validate=True)
            private_key = serialization.load_pem_private_key(key_bytes, password=None, backend=default_backend())
        except (ValueError, TypeError) as error:
            return {'success': False, 'error': f'设备私钥格式无效: {error}'}

        endpoint_paths = paths or {}
        initiate_path = endpoint_paths.get('init_path', '/device/initiate')
        authenticate_path = endpoint_paths.get('auth_path', '/device/authenticate')
        event_path = endpoint_paths.get('event_path', '/event/events')
        session = requests.Session()
        try:
            token = BusinessTools._get_edge_token(session, base_url, device_id, private_key, initiate_path, authenticate_path, timeout_seconds)
            event_ids = []
            for index, event in enumerate(events):
                response = session.post(
                    BusinessTools._url(base_url, event_path),
                    json=event,
                    headers={'Authorization': token, 'x-agent': 'web', 'Content-Type': 'application/json'},
                    timeout=timeout_seconds,
                )
                if response.status_code == 401:
                    token = BusinessTools._get_edge_token(session, base_url, device_id, private_key, initiate_path, authenticate_path, timeout_seconds)
                    response = session.post(
                        BusinessTools._url(base_url, event_path),
                        json=event,
                        headers={'Authorization': token, 'x-agent': 'web', 'Content-Type': 'application/json'},
                        timeout=timeout_seconds,
                    )
                response.raise_for_status()
                event_id = response.json().get('event', {}).get('id')
                if not event_id:
                    return {'success': False, 'error': '事件上报响应缺少 event.id。'}
                if media_groups:
                    BusinessTools._upload_and_complete_media(
                        session=session,
                        event_response=response.json(),
                        event_id=event_id,
                        base_url=base_url,
                        event_path=event_path,
                        headers={'Authorization': token, 'x-agent': 'web', 'Content-Type': 'application/json'},
                        media_group=media_groups[index],
                        s3_url=s3_url,
                        timeout_seconds=timeout_seconds,
                    )
                event_ids.append(event_id)
            return {'success': True, 'event_ids': event_ids}
        except (requests.RequestException, ValueError) as error:
            return {'success': False, 'error': f'真实事件上报失败: {error}'}

    @staticmethod
    def _get_edge_token(
        session: requests.Session,
        base_url: str,
        device_id: str,
        private_key: Any,
        initiate_path: str,
        authenticate_path: str,
        timeout_seconds: int,
    ) -> str:
        initiate_response = session.post(
            BusinessTools._url(base_url, initiate_path),
            json={'deviceId': device_id},
            headers={'x-agent': 'web'},
            timeout=timeout_seconds,
        )
        initiate_response.raise_for_status()
        challenge = initiate_response.json().get('challenge')
        if not challenge:
            raise ValueError('设备认证响应缺少 challenge。')
        challenge_text = BusinessTools._decrypt_edge_value(challenge, private_key)
        authenticate_response = session.post(
            BusinessTools._url(base_url, authenticate_path),
            json={'deviceId': device_id, 'challenge': challenge_text},
            timeout=timeout_seconds,
        )
        authenticate_response.raise_for_status()
        encrypted_token = authenticate_response.json().get('token')
        if not encrypted_token:
            raise ValueError('设备认证响应缺少 token。')
        return BusinessTools._decrypt_edge_value(encrypted_token, private_key)

    @staticmethod
    def _decrypt_edge_value(value: str, private_key: Any) -> str:
        encrypted = base64.b64decode(value)
        chunk_size = private_key.key_size // 8
        decrypted = b''.join(
            private_key.decrypt(
                encrypted[index:index + chunk_size],
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA512()),
                    algorithm=hashes.SHA512(),
                    label=None,
                ),
            )
            for index in range(0, len(encrypted), chunk_size)
        )
        return decrypted.decode('utf-8')

    @staticmethod
    def _url(base_url: str, path: str) -> str:
        return f'{base_url.rstrip("/")}/{path.lstrip("/")}'

    @staticmethod
    def collect_event_media(media_root: Path, relative_path: str) -> list[dict[str, Path | None]]:
        root = media_root.resolve()
        candidate = (root / relative_path).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError('素材路径必须位于受控事件素材目录内。')
        if candidate.is_file():
            image_paths = [candidate]
        elif candidate.is_dir():
            image_paths = sorted(candidate.glob('*_image_0.jpeg'))
        else:
            raise ValueError('素材路径不存在或不包含可用的 _image_0.jpeg 文件。')
        if not image_paths:
            raise ValueError('目录中未找到 _image_0.jpeg 事件素材。')
        return [BusinessTools._media_group(image_path) for image_path in image_paths]

    @staticmethod
    def _media_group(image_0: Path) -> dict[str, Path | None]:
        marker = '_snap_image_0.'
        if marker not in image_0.name:
            return {'image_0': image_0, 'image_1': None, 'video_0': None}
        prefix, extension = image_0.name.split(marker, maxsplit=1)
        image_1 = image_0.with_name(f'{prefix}_snap_image_1.{extension}')
        video_0 = image_0.with_name(f'{prefix}_video_video_0.mp4')
        return {
            'image_0': image_0,
            'image_1': image_1 if image_1.is_file() else None,
            'video_0': video_0 if video_0.is_file() else None,
        }

    @staticmethod
    def _upload_and_complete_media(
        session: requests.Session,
        event_response: dict[str, Any],
        event_id: str,
        base_url: str,
        event_path: str,
        headers: dict[str, str],
        media_group: dict[str, Path | None],
        s3_url: str,
        timeout_seconds: int,
    ) -> None:
        if not s3_url:
            raise ValueError('所选环境未配置 edge.s3_url，无法上传事件素材。')
        upload_forms = {
            task.get('id'): task.get('media', {}).get('preSignedUrl', {})
            for task in event_response.get('event', {}).get('tasks', [])
        }
        image_tasks = []
        for task_id in ('image_0', 'image_1'):
            media_path = media_group.get(task_id)
            if media_path is None:
                continue
            BusinessTools._upload_media(session, media_path, upload_forms.get(task_id, {}), s3_url, timeout_seconds)
            with Image.open(media_path) as image:
                image_tasks.append({
                    'id': task_id,
                    'media': {'meta': {'index': 1 if task_id == 'image_0' else 2, 'size': media_path.stat().st_size, 'width': image.width, 'height': image.height, 'type': 1 if task_id == 'image_0' else 2}},
                })
        if image_tasks:
            response = session.put(
                BusinessTools._url(base_url, event_path),
                json={'event': {'id': event_id, 'tasks': image_tasks}},
                headers=headers,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        video_path = media_group.get('video_0')
        if video_path is not None:
            BusinessTools._upload_media(session, video_path, upload_forms.get('video_0', {}), s3_url, timeout_seconds)
            response = session.put(
                BusinessTools._url(base_url, event_path),
                json={
                    'event': {
                        'id': event_id,
                        'tasks': [
                            {
                                'id': 'video_0',
                                'media': {
                                    'meta': {
                                        'size': video_path.stat().st_size,
                                        'startedAt': int(time()),
                                        'endedAt': int(time()) + 10,
                                    },
                                },
                            },
                        ],
                    },
                },
                headers=headers,
                timeout=timeout_seconds,
            )
            response.raise_for_status()

    @staticmethod
    def _upload_media(session: requests.Session, media_path: Path, pre_signed: dict[str, Any], s3_url: str, timeout_seconds: int) -> None:
        form_data = pre_signed.get('data')
        if not isinstance(form_data, dict):
            raise ValueError(f'事件响应缺少 {media_path.name} 的预签名上传表单。')
        with media_path.open('rb') as media_file:
            response = session.post(s3_url, data=form_data, files={'file': media_file}, timeout=timeout_seconds)
        if response.status_code != 204:
            raise ValueError(f'素材上传失败: {media_path.name}，状态码 {response.status_code}。')


    @staticmethod
    def _template(alert_type: AlertType) -> dict[str, Any]:
        object_info: dict[str, Any] = {
            'FaceInfoList': None,
            'FaceNum': 0,
            'FirePointsInfoList': None,
            'FirePointsNum': 0,
            'NonMotorVehicleInfoList': None,
            'NonMotorVehicleNum': 0,
            'PersonInfoList': None,
            'PersonNum': 0,
            'VehicleInfoList': None,
            'VehicleNum': 0,
        }
        if alert_type == 'person':
            object_info['PersonInfoList'] = [{
                'AppearTime': '', 'DisAppearTime': '', 'Feature': '', 'FeatureVersion': '',
                'LargePicAttachIndex': 1, 'SmallPicAttachIndex': 2, 'PersonID': 1047,
                'Position': '2395,6450;3242,9196', 'Confidence': 0,
                'RuleInfo': {'PointList': None, 'PointNum': 0, 'RuleType': 0, 'TriggerType': 0},
                'AttributeInfo': {
                    'AgeRange': 98, 'BagFlag': 98, 'BodyToward': 0, 'CoatColor': 2,
                    'Gender': 98, 'HairLength': 0, 'ShoesTubeLength': 0,
                    'SleevesLength': 0, 'TrousersColor': 3, 'TrousersLength': 0,
                },
            }]
            object_info['PersonNum'] = 1
        else:
            object_info['VehicleInfoList'] = [{
                'ID': 1, 'Position': '3109,6136;5390,8266', 'LargePicAttachIndex': 1,
                'SmallPicAttachIndex': 2, 'Feature': '', 'FeatureVersion': '', 'Confidence': 0,
                'AppearTime': '', 'DisAppearTime': '',
                'RuleInfo': {'PointList': None, 'PointNum': 0, 'RuleType': 0, 'TriggerType': 0},
                'VehicleAttributeInfo': {
                    'DriverSeatBeltStatus': '', 'Type': 998, 'VehicleBrand': '99',
                    'AimStatus': '', 'ImageDirection': 0, 'Color': 100,
                    'DriverMobileStatus': '', 'DriverSunVisorStatus': '',
                    'CodriverSunVisorStatus': '', 'PendantStatus': '', 'SpeedType': 0,
                },
            }]
            object_info['VehicleNum'] = 1

        return {
            'event': {
                'tasks': [
                    {'id': 'image_0', 'media': {'ext': 'jpeg', 'type': 'image', 'meta': {'type': 1}}},
                    {'id': 'image_1', 'media': {'ext': 'jpeg', 'type': 'image', 'meta': {'type': 2}}},
                    {'id': 'video_0', 'media': {'ext': 'mp4', 'type': 'video', 'meta': {}}},
                ],
                'meta': {'camera': {'macAddress': 'xxx', 'remoteIndex': 1}, 'uuid': 'xxx'},
                'raw': {
                    'alarm': {
                        'AlarmLevel': 0, 'AlarmSrcID': 3, 'AlarmSrcName': '', 'AlarmSrcType': 8,
                        'AlarmType': 'SmartMotionDetectOn', 'RelatedID': 'rk1YOHYnSfkzoph', 'TimeStamp': 'xxx',
                    },
                    'struct': {
                        'RelatedID': 'rk1YOHYnSfkzoph', 'SrcID': 3, 'SrcName': 'xxx', 'TimeStamp': 'xxx',
                        'StructureInfo': {
                            'ImageNum': 2,
                            'ImageInfoList': [
                                {'CaptureTime': 'xxx', 'Format': 0, 'Height': 0, 'Index': 1, 'Size': 400312, 'Type': 1, 'Width': 0, 'RealImageMeta': {'format': 'jpeg', 'height': 1520, 'path': '/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_1.jpg', 'size': 404576, 'width': 2688}},
                                {'CaptureTime': 'xxx', 'Format': 0, 'Height': 0, 'Index': 2, 'Size': 48564, 'Type': 2, 'Width': 0, 'RealImageMeta': {'format': 'jpeg', 'height': 448, 'path': '/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_2.jpg', 'size': 20894, 'width': 256}},
                            ],
                            'ObjInfo': object_info,
                        },
                    },
                },
            },
        }