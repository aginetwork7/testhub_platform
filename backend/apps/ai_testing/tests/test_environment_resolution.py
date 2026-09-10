"""Regression tests for environment resolution from AI case task descriptions."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_testing.views import resolve_environment_configuration_from_task
from apps.core.models import EnvironmentConfiguration


class EnvironmentResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username='resolver-tester', password='x')
        cls.default_env = EnvironmentConfiguration.objects.create(
            name='test-2 环境',
            environment='test-2',
            web_url='https://web-test-2.example.com',
            is_default=True,
        )
        cls.test_env = EnvironmentConfiguration.objects.create(
            name='test 环境',
            environment='test',
            web_url='https://web-test.example.com',
        )
        cls.demo_env = EnvironmentConfiguration.objects.create(
            name='demo 环境',
            environment='demo',
            web_url='https://web-demo.example.com',
        )
        cls.dev_env = EnvironmentConfiguration.objects.create(
            name='dev 环境',
            environment='dev',
            web_url='https://web-dev.example.com',
        )
        cls.sam_env = EnvironmentConfiguration.objects.create(
            name='sam 环境',
            environment='sam',
            web_url='https://web-sam.example.com',
        )
        cls.test3_env = EnvironmentConfiguration.objects.create(
            name='test-3 环境',
            environment='test-3',
            web_url='https://web-test-3.example.com',
        )

    def resolve(self, text):
        return resolve_environment_configuration_from_task(text, self.user)

    def test_email_address_tokens_do_not_select_named_environment(self):
        configuration = self.resolve('Email输入框填写 ai@test.com，然后点击创建')

        self.assertEqual(configuration, self.default_env)

    def test_url_tokens_do_not_select_named_environment(self):
        configuration = self.resolve('打开 https://demo.example.com/agi7/api 的接口文档')

        self.assertEqual(configuration, self.default_env)

    def test_standalone_latin_environment_name_still_matches(self):
        self.assertEqual(self.resolve('在 test 环境执行下面步骤'), self.test_env)
        self.assertEqual(self.resolve('切换到 demo 环境继续'), self.demo_env)
        self.assertEqual(self.resolve('使用 test-2 环境执行'), self.default_env)

    def test_explicit_chinese_environment_name_still_matches(self):
        self.assertEqual(self.resolve('在 test-3 环境执行下面步骤'), self.test3_env)

    def test_tie_prefers_default_environment(self):
        configuration = self.resolve('先跑 test-2 再跑 test-3，两个环境都要覆盖')

        self.assertEqual(configuration, self.default_env)

    def test_tie_without_default_stays_fail_safe(self):
        configuration = self.resolve('dev 与 sam 的差异对比')

        self.assertIsNone(configuration)

    def test_display_name_match_outranks_bare_code_deterministically(self):
        for _ in range(5):
            configuration = self.resolve('dev 与 sam 环境的差异对比')

            self.assertEqual(configuration, self.sam_env)
