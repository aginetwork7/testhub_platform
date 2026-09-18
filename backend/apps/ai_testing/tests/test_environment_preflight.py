"""执行前环境自检：未配置 AI 测试的环境应当立刻明确报错，而不是在 about:blank 上跑完整个用例。"""

from django.test import SimpleTestCase

from apps.ai_testing.execution.environment_preflight import (
    collect_environment_problems,
    describe_environment_problems,
    steps_need_data_factory,
    steps_need_target_device,
    web_url_looks_like_an_api_root,
)


class _Environment:
    def __init__(self, name='test-2', web_url='https://test-web-2.agi7.ai', runtime_settings=None, auth_profiles=None):
        self.id = 1
        self.name = name
        self.web_url = web_url
        self.runtime_settings = runtime_settings if runtime_settings is not None else {
            'ai_testing_browser': {'login_path': '/login', 'auth_profile': 'customer'},
        }
        self.auth_profiles = auth_profiles if auth_profiles is not None else {
            'customer': {'username': 'customer@test.com', 'password': '12345678'},
        }


BROWSER_STEP = {'executor': 'browser', 'description': 'Click the Alerts icon.'}


class ConfiguredEnvironmentTests(SimpleTestCase):
    def test_a_fully_configured_environment_passes(self) -> None:
        self.assertEqual(collect_environment_problems(_Environment(), [BROWSER_STEP], 'goal'), [])


class MissingConfigurationTests(SimpleTestCase):
    def test_a_missing_block_names_what_to_add(self) -> None:
        # 正式环境 8 个运行环境里有 7 个从未为 AI 测试配置过，这是预期状态，报错要说清怎么补。
        problems = collect_environment_problems(_Environment(runtime_settings={}), [BROWSER_STEP])
        self.assertEqual(len(problems), 1)
        self.assertIn('ai_testing_browser', problems[0])
        self.assertIn('login_path', problems[0])

    def test_an_empty_login_path_is_reported(self) -> None:
        env = _Environment(runtime_settings={'ai_testing_browser': {'login_path': '  '}})
        self.assertTrue(any('login_path' in problem for problem in collect_environment_problems(env, [BROWSER_STEP])))

    def test_a_missing_web_url_is_reported(self) -> None:
        self.assertTrue(any('web_url' in p for p in collect_environment_problems(_Environment(web_url=''), [BROWSER_STEP])))

    def test_incomplete_credentials_are_reported(self) -> None:
        env = _Environment(auth_profiles={'customer': {'username': 'customer@test.com'}})
        problems = collect_environment_problems(env, [BROWSER_STEP])
        self.assertTrue(any('登录配置不完整' in problem for problem in problems))

    def test_no_environment_at_all_is_reported(self) -> None:
        self.assertEqual(len(collect_environment_problems(None, [BROWSER_STEP])), 1)


class WebUrlHeuristicTests(SimpleTestCase):
    """填成接口地址是最常见的一种「配了但配错」，但它只作为附带提示，不单独拦截。"""

    def test_an_api_root_is_recognised(self) -> None:
        for url in ('https://test-web-2.agi7.ai/agi7/api', 'https://x.test/api/', 'https://x.test/v1'):
            with self.subTest(url=url):
                self.assertTrue(web_url_looks_like_an_api_root(url))

    def test_an_ordinary_site_url_is_not_flagged(self) -> None:
        for url in ('https://test-web-2.agi7.ai', 'https://x.test/dashboard', ''):
            with self.subTest(url=url):
                self.assertFalse(web_url_looks_like_an_api_root(url))

    def test_the_hint_never_fails_a_healthy_environment(self) -> None:
        env = _Environment(web_url='https://test-web-2.agi7.ai/agi7/api')
        self.assertEqual(collect_environment_problems(env, [BROWSER_STEP]), [])

    def test_the_hint_is_appended_when_something_else_is_wrong(self) -> None:
        env = _Environment(web_url='https://test-web-2.agi7.ai/agi7/api', runtime_settings={})
        problems = collect_environment_problems(env, [BROWSER_STEP])
        self.assertTrue(any('接口地址' in problem for problem in problems))


class PerRunRequirementTests(SimpleTestCase):
    """数据工厂与目标设备按本次用例实际需要检查，不需要的用例不应因此失败。"""

    def test_data_factory_is_required_only_when_a_step_uses_it(self) -> None:
        env = _Environment()
        self.assertEqual(collect_environment_problems(env, [BROWSER_STEP]), [])
        factory_step = {'executor': 'data_factory', 'resource_type': 'alert_event'}
        problems = collect_environment_problems(env, [BROWSER_STEP, factory_step])
        self.assertTrue(any('ai_testing_data_factory' in problem for problem in problems))

    def test_steps_need_data_factory_detects_the_executor(self) -> None:
        self.assertFalse(steps_need_data_factory([BROWSER_STEP]))
        self.assertTrue(steps_need_data_factory([{'executor': 'data_factory'}]))
        self.assertFalse(steps_need_data_factory(None))

    def test_the_target_device_is_required_only_when_the_run_mentions_it(self) -> None:
        env = _Environment()
        # 暗色模式用例不该因为环境没配摄像头而失败。
        self.assertEqual(collect_environment_problems(env, [BROWSER_STEP], 'Switch to dark mode'), [])
        device_step = {'executor': 'browser', 'description': 'Open the default test device camera.'}
        problems = collect_environment_problems(env, [device_step], 'goal')
        self.assertTrue(any('main_device' in problem for problem in problems))

    def test_a_configured_device_satisfies_the_check(self) -> None:
        env = _Environment(runtime_settings={
            'ai_testing_browser': {'login_path': '/login', 'auth_profile': 'customer'},
            'api': {'edge': {'main_device': {'site': '萧山区', 'device_id': 'nvr_5003'}}},
        })
        device_step = {'executor': 'browser', 'description': 'Open the default test device camera.'}
        self.assertEqual(collect_environment_problems(env, [device_step], 'goal'), [])

    def test_steps_need_target_device_reads_the_goal_too(self) -> None:
        self.assertTrue(steps_need_target_device([], '在默认测试设备上打开直播'))
        self.assertFalse(steps_need_target_device([BROWSER_STEP], 'Switch to dark mode'))


class FailureMessageTests(SimpleTestCase):
    def test_the_message_names_the_environment_and_reads_as_an_environment_problem(self) -> None:
        message = describe_environment_problems(_Environment(name='demo'), ['缺少 ai_testing_browser'])
        # dispatch 依据这句把结果归类为 inconclusive：未配置不是产品缺陷。
        self.assertIn('被测环境不可用', message)
        self.assertIn('demo', message)
        self.assertIn('缺少 ai_testing_browser', message)

    def test_the_runner_fails_before_launching_a_browser(self) -> None:
        import inspect

        from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent

        source = inspect.getsource(PyUICompatAgent.run_full_process)
        self.assertLess(source.index('collect_environment_problems'), source.index('async_playwright'))
        self.assertIn('raise EnvironmentBootstrapError(message)', source)
