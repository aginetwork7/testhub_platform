from django.test import TestCase

from apps.data_factory.tools.business_tools import BusinessTools

class ConstructAlertEventTests(TestCase):
	def test_constructs_person_event_with_selected_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(rule_type=1)

		rule_info = result['result']['event']['raw']['struct']['StructureInfo']['ObjInfo']['PersonInfoList'][0]['RuleInfo']

		self.assertTrue(result['success'])
		self.assertEqual(rule_info, {'PointList': None, 'PointNum': 0, 'RuleType': 1, 'TriggerType': 0})

	def test_constructs_vehicle_event_with_selected_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(alert_type='vehicle', rule_type=3)

		rule_info = result['result']['event']['raw']['struct']['StructureInfo']['ObjInfo']['VehicleInfoList'][0]['RuleInfo']

		self.assertTrue(result['success'])
		self.assertEqual(rule_info, {'PointList': None, 'PointNum': 0, 'RuleType': 3, 'TriggerType': 0})

	def test_rejects_unsupported_rule_type(self) -> None:
		result = BusinessTools.construct_alert_event(rule_type=4)

		self.assertFalse(result['success'])
		self.assertIn('规则类型', result['error'])


# ---------------------------------------------------------------------------
# 事件素材的两个根：基准集受版本管理且只读，上传集可写且不入库。
# ---------------------------------------------------------------------------
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.data_factory import asset_roots


class RootSeparationTests(SimpleTestCase):
    def test_the_baseline_root_lives_in_the_code_tree(self) -> None:
        self.assertTrue(str(asset_roots.BASELINE_ROOT).endswith('data_factory/data_warehouse/events'))

    def test_the_upload_root_lives_under_media(self) -> None:
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                # MEDIA_ROOT 已被 gitignore 覆盖，写在这里不会弄脏 git 工作区。
                self.assertEqual(asset_roots.upload_root(), Path(media) / 'data_factory' / 'events')

    def test_uploads_take_priority_over_the_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                roots = asset_roots.read_roots()
        # 顺序固定，不依赖文件系统返回序，否则界面上的素材列表会无缘无故抖动。
        self.assertEqual(roots[1], asset_roots.BASELINE_ROOT)
        self.assertNotEqual(roots[0], asset_roots.BASELINE_ROOT)


class BaselineProtectionTests(SimpleTestCase):
    def test_a_baseline_file_is_recognised(self) -> None:
        self.assertTrue(asset_roots.is_baseline(asset_roots.BASELINE_ROOT / 'person' / 'gun_snap_image_0.jpeg'))

    def test_an_uploaded_file_is_not_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                self.assertFalse(asset_roots.is_baseline(asset_roots.upload_root() / 'person' / 'x_snap_image_0.jpeg'))

    def test_the_delete_endpoint_refuses_baseline_assets(self) -> None:
        import inspect

        from apps.data_factory.views import DataFactoryViewSet

        source = inspect.getsource(DataFactoryViewSet.warehouse_group)
        # 界面上删掉基准素材会让 git 工作区出现删除态改动，正式环境下一次 git pull 因此冲突。
        self.assertIn('asset_roots.is_baseline(primary_path)', source)
        self.assertIn('HTTP_403_FORBIDDEN', source)

    def test_the_directory_delete_endpoint_refuses_baseline_directories(self) -> None:
        import inspect

        from apps.data_factory.views import DataFactoryViewSet

        source = inspect.getsource(DataFactoryViewSet.warehouse_directory)
        self.assertIn('asset_roots.BASELINE_ROOT', source)
        self.assertIn('HTTP_403_FORBIDDEN', source)

    def test_uploads_only_ever_write_to_the_upload_root(self) -> None:
        import inspect

        from apps.data_factory.views import DataFactoryViewSet

        source = inspect.getsource(DataFactoryViewSet.warehouse_upload) if hasattr(
            DataFactoryViewSet, 'warehouse_upload') else ''
        if not source:
            import apps.data_factory.views as views_module
            source = inspect.getsource(views_module)
        self.assertIn('asset_roots.ensure_upload_root(category)', source)


class PathTraversalTests(SimpleTestCase):
    def test_escaping_the_root_is_refused(self) -> None:
        for bad in ('../../etc/passwd', 'person/../../../etc/passwd'):
            with self.subTest(path=bad):
                self.assertIsNone(asset_roots.resolve_within(asset_roots.BASELINE_ROOT, bad))

    def test_a_path_inside_the_root_resolves(self) -> None:
        resolved = asset_roots.resolve_within(asset_roots.BASELINE_ROOT, 'person')
        self.assertIsNotNone(resolved)
        self.assertTrue(str(resolved).endswith('/person'))


class MultiRootCollectionTests(SimpleTestCase):
    def test_both_roots_are_searched(self) -> None:
        with tempfile.TemporaryDirectory() as upload:
            category = Path(upload) / 'person'
            category.mkdir(parents=True)
            (category / 'uploaded_snap_image_0.jpeg').write_bytes(b'x')
            groups = BusinessTools.collect_event_media_multi(
                [Path(upload), asset_roots.BASELINE_ROOT], 'person',
            )
            names = {group['image_0'].name for group in groups}
        self.assertIn('uploaded_snap_image_0.jpeg', names)   # 上传集
        self.assertIn('gun_snap_image_0.jpeg', names)        # 基准集

    def test_the_first_root_wins_on_a_name_clash(self) -> None:
        with tempfile.TemporaryDirectory() as upload:
            category = Path(upload) / 'person'
            category.mkdir(parents=True)
            (category / 'gun_snap_image_0.jpeg').write_bytes(b'overridden')
            groups = BusinessTools.collect_event_media_multi(
                [Path(upload), asset_roots.BASELINE_ROOT], 'person',
            )
            matches = [g for g in groups if g['image_0'].name == 'gun_snap_image_0.jpeg']
        self.assertEqual(len(matches), 1)
        self.assertTrue(str(matches[0]['image_0']).startswith(upload))

    def test_a_missing_root_is_skipped_not_fatal(self) -> None:
        groups = BusinessTools.collect_event_media_multi(
            [Path('/nonexistent-root'), asset_roots.BASELINE_ROOT], 'person',
        )
        self.assertTrue(groups)

    def test_nothing_anywhere_still_raises(self) -> None:
        with self.assertRaises(ValueError):
            BusinessTools.collect_event_media_multi([asset_roots.BASELINE_ROOT], 'no-such-category')
