from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ui_automation.models import Element, LocatorStrategy, TestCase, TestCaseStep, UiProject


TARGET_URL = 'https://test-web-2.agi7.ai/login'
PROJECT_NAME = 'Alpha Vision Login Demo'
CASE_NAME = 'Alpha Vision Login Success'


@dataclass(frozen=True)
class ElementSeed:
    key: str
    name: str
    element_type: str
    strategy_name: str
    locator_value: str
    description: str
    page: str = 'login'


@dataclass(frozen=True)
class StepSeed:
    step_number: int
    action_type: str
    description: str
    element_key: Optional[str] = None
    input_value: str = ''
    wait_time: int = 1000
    assert_type: str = ''
    assert_value: str = ''


ELEMENT_SEEDS: tuple[ElementSeed, ...] = (
    ElementSeed(
        key='email_input',
        name='Login Email Input',
        element_type='INPUT',
        strategy_name='name',
        locator_value='email',
        description='Alpha Vision 登录页邮箱输入框',
    ),
    ElementSeed(
        key='password_input',
        name='Login Password Input',
        element_type='INPUT',
        strategy_name='name',
        locator_value='password',
        description='Alpha Vision 登录页密码输入框',
    ),
    ElementSeed(
        key='login_button',
        name='Login Submit Button',
        element_type='BUTTON',
        strategy_name='CSS',
        locator_value='button[type="submit"]',
        description='Alpha Vision 登录提交按钮',
    ),
)


STEP_SEEDS: tuple[StepSeed, ...] = (
    StepSeed(
        step_number=1,
        action_type='waitFor',
        element_key='email_input',
        wait_time=15000,
        description='等待邮箱输入框出现',
    ),
    StepSeed(
        step_number=2,
        action_type='fill',
        element_key='email_input',
        input_value='ms_customer_1@outlook.com',
        wait_time=5000,
        description='输入邮箱账号',
    ),
    StepSeed(
        step_number=3,
        action_type='fill',
        element_key='password_input',
        input_value='ms000000',
        wait_time=5000,
        description='输入登录密码',
    ),
    StepSeed(
        step_number=4,
        action_type='click',
        element_key='login_button',
        wait_time=5000,
        description='点击登录按钮',
    ),
    StepSeed(
        step_number=5,
        action_type='wait',
        wait_time=3000,
        description='等待页面跳转稳定',
    ),
    StepSeed(
        step_number=6,
        action_type='assert',
        assert_type='urlContains',
        assert_value='/dashboard',
        wait_time=5000,
        description='断言当前页面 URL 已进入 dashboard',
    ),
)


class Command(BaseCommand):
    help = '初始化 Alpha Vision 登录演示用 UI 自动化项目、元素和测试用例'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--owner',
            dest='owner',
            help='项目归属用户，可传 username 或 email。未提供时优先使用第一个超级用户。',
        )
        parser.add_argument(
            '--project-name',
            dest='project_name',
            default=PROJECT_NAME,
            help=f'UI 自动化项目名称，默认: {PROJECT_NAME}',
        )
        parser.add_argument(
            '--case-name',
            dest='case_name',
            default=CASE_NAME,
            help=f'测试用例名称，默认: {CASE_NAME}',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅打印将要执行的操作，不写入数据库。',
        )

    def handle(self, *args, **options) -> None:
        owner_identifier = options['owner']
        project_name = options['project_name']
        case_name = options['case_name']
        dry_run = options['dry_run']

        owner = self._resolve_owner(owner_identifier)
        self.stdout.write(self.style.SUCCESS(f'使用用户: {owner.username}'))
        self.stdout.write(f'目标项目: {project_name}')
        self.stdout.write(f'目标用例: {case_name}')
        if dry_run:
            self.stdout.write(self.style.WARNING('当前为 dry-run 模式，不会写入数据库。'))

        self._ensure_locator_strategies_exist(strategy_names=(seed.strategy_name for seed in ELEMENT_SEEDS))

        if dry_run:
            self._print_plan(owner=owner.username, project_name=project_name, case_name=case_name)
            return

        with transaction.atomic():
            project = self._upsert_project(project_name=project_name, owner=owner)
            elements = self._upsert_elements(project=project, owner=owner)
            test_case = self._upsert_test_case(case_name=case_name, project=project, owner=owner)
            self._replace_steps(test_case=test_case, elements=elements)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('初始化完成。'))
        self.stdout.write(f'项目 ID: {project.id}')
        self.stdout.write(f'测试用例 ID: {test_case.id}')
        self.stdout.write('执行建议:')
        self.stdout.write('  1. python manage.py init_locator_strategies')
        self.stdout.write('  2. python -m playwright install chromium')
        self.stdout.write(
            f'  3. 在 UI 自动化页面运行用例，或调用 POST /api/ui-automation/test-cases/{test_case.id}/run/'
        )

    def _resolve_owner(self, owner_identifier: Optional[str]):
        user_model = get_user_model()

        if owner_identifier:
            owner = user_model.objects.filter(username=owner_identifier).first()
            if owner is None:
                owner = user_model.objects.filter(email=owner_identifier).first()
            if owner is None:
                raise CommandError(f'未找到用户: {owner_identifier}')
            return owner

        owner = user_model.objects.filter(is_superuser=True).order_by('id').first()
        if owner is not None:
            return owner

        owner = user_model.objects.order_by('id').first()
        if owner is not None:
            return owner

        raise CommandError('当前系统没有可用用户，请先创建用户后再执行此命令。')

    def _ensure_locator_strategies_exist(self, strategy_names: Iterable[str]) -> None:
        missing_names = []
        for strategy_name in strategy_names:
            strategy = LocatorStrategy.objects.filter(name__iexact=strategy_name).first()
            if strategy is None:
                missing_names.append(strategy_name)

        if missing_names:
            joined = ', '.join(sorted(set(missing_names)))
            raise CommandError(
                f'缺少定位策略: {joined}。请先执行 python manage.py init_locator_strategies'
            )

    def _print_plan(self, owner: str, project_name: str, case_name: str) -> None:
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('将创建或更新以下数据：'))
        self.stdout.write(f'  - 项目: {project_name} ({TARGET_URL})')
        self.stdout.write(f'  - 归属用户: {owner}')
        self.stdout.write(f'  - 用例: {case_name}')
        self.stdout.write('  - 元素:')
        for seed in ELEMENT_SEEDS:
            self.stdout.write(f'    * {seed.name}: {seed.strategy_name}={seed.locator_value}')
        self.stdout.write('  - 步骤:')
        for step in STEP_SEEDS:
            self.stdout.write(f'    * {step.step_number}. {step.action_type} - {step.description}')

    def _upsert_project(self, project_name: str, owner):
        project, created = UiProject.objects.update_or_create(
            name=project_name,
            defaults={
                'description': 'Alpha Vision 登录演示项目，由 init_alpha_vision_login_case 命令维护。',
                'status': 'active',
                'base_url': TARGET_URL,
                'owner': owner,
            },
        )
        action = '创建' if created else '更新'
        self.stdout.write(self.style.SUCCESS(f'{action}项目: {project.name}'))
        if not project.members.filter(id=owner.id).exists():
            project.members.add(owner)
        return project

    def _upsert_elements(self, project: UiProject, owner) -> dict[str, Element]:
        elements: dict[str, Element] = {}
        for seed in ELEMENT_SEEDS:
            strategy = LocatorStrategy.objects.filter(name__iexact=seed.strategy_name).get()
            element, created = Element.objects.update_or_create(
                project=project,
                name=seed.name,
                defaults={
                    'description': seed.description,
                    'element_type': seed.element_type,
                    'locator_strategy': strategy,
                    'locator_value': seed.locator_value,
                    'page': seed.page,
                    'created_by': owner,
                    'is_enabled': True,
                    'is_visible': True,
                    'wait_timeout': 10,
                    'validation_status': 'UNKNOWN',
                },
            )
            action = '创建' if created else '更新'
            self.stdout.write(f'{action}元素: {element.name}')
            elements[seed.key] = element
        return elements

    def _upsert_test_case(self, case_name: str, project: UiProject, owner) -> TestCase:
        test_case, created = TestCase.objects.update_or_create(
            project=project,
            name=case_name,
            defaults={
                'description': '验证 Alpha Vision 登录成功后跳转到 dashboard。',
                'status': 'ready',
                'priority': 'high',
                'created_by': owner,
            },
        )
        action = '创建' if created else '更新'
        self.stdout.write(f'{action}用例: {test_case.name}')
        return test_case

    def _replace_steps(self, test_case: TestCase, elements: dict[str, Element]) -> None:
        deleted_count, _ = test_case.steps.all().delete()
        if deleted_count:
            self.stdout.write(f'重建步骤: 已删除旧步骤 {deleted_count} 条')

        steps = []
        for seed in STEP_SEEDS:
            element = elements.get(seed.element_key) if seed.element_key else None
            steps.append(
                TestCaseStep(
                    test_case=test_case,
                    step_number=seed.step_number,
                    action_type=seed.action_type,
                    element=element,
                    input_value=seed.input_value,
                    wait_time=seed.wait_time,
                    assert_type=seed.assert_type,
                    assert_value=seed.assert_value,
                    description=seed.description,
                )
            )

        TestCaseStep.objects.bulk_create(steps)
        self.stdout.write(f'创建步骤: {len(steps)} 条')