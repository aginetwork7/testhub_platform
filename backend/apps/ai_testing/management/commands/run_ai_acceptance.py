"""Run AI intelligent-test cases for N consecutive rounds through the same launch path as the UI."""

import json
import time
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai_testing.execution.dispatch import launch_case_execution
from apps.ai_testing.models import AICase, AIExecutionRecord
from apps.core.models import EnvironmentConfiguration

TERMINAL_STATUSES = {'passed', 'failed', 'inconclusive', 'stopped'}


class Command(BaseCommand):
    help = '按轮次串行执行 AI 用例并汇总结果（默认与 UI 相同的 planner_v2 路径）。'

    def add_arguments(self, parser):
        parser.add_argument('--cases', default='', help='逗号分隔的 AICase id；与 --project 二选一')
        parser.add_argument('--project', type=int, default=None, help='按项目挑选用例（可配合 --case-prefix）')
        parser.add_argument('--case-prefix', default='', help='仅运行 case_number 以该前缀开头的用例')
        parser.add_argument('--rounds', type=int, default=1)
        parser.add_argument('--env-id', type=int, default=None, help='EnvironmentConfiguration id；缺省取默认环境')
        parser.add_argument('--execution-mode', default='planner_v2')
        parser.add_argument('--no-cache', action='store_true', help='禁用动作缓存/经验复用')
        parser.add_argument('--force-replan', action='store_true', help='忽略计划缓存重新生成全局计划（步骤动作缓存不受影响）')
        parser.add_argument('--env-retries', type=int, default=1, help='被测环境不可用（登录页未渲染等）时每个用例最多重跑的次数，0 表示不重跑')
        parser.add_argument('--user', default='', help='执行人用户名；缺省取第一个超级用户')
        parser.add_argument('--timeout', type=int, default=2400, help='单用例最长等待秒数')
        parser.add_argument('--poll', type=float, default=5.0, help='轮询间隔秒数')
        parser.add_argument('--json', default='', help='将结果写入该 JSON 文件')
        parser.add_argument(
            '--assert-cold', action='store_true',
            help='断言每次运行都没有复用已验证计划；与 --no-cache --force-replan 同用，'
                 '防止开关未生效时跑出一份看起来通过、实则是热运行的报告',
        )

    def handle(self, *args, **options):
        cases = self._select_cases(options)
        if not cases:
            raise CommandError('没有匹配的用例。')
        user = self._select_user(options['user'])
        environment = self._select_environment(options['env_id'])
        rounds = max(1, int(options['rounds']))
        results = []
        env_retries = 0
        for round_number in range(1, rounds + 1):
            self.stdout.write(f'=== ROUND {round_number} ===')
            for case in cases:
                outcome = self._run_case(case, user, environment, options)
                retries_left = max(0, int(options.get('env_retries') or 0))
                # An environment outage (login page never rendered) is not a verdict on the case; rerun it.
                while outcome['status'] == 'inconclusive' and retries_left > 0 and self._environment_failure(outcome['record_id']):
                    retries_left -= 1
                    env_retries += 1
                    self.stdout.write(
                        f"ENV RETRY case={case.id} {case.case_number or case.name}: record={outcome['record_id']} 被测环境不可用，重跑该用例"
                    )
                    outcome = self._run_case(case, user, environment, options)
                outcome['round'] = round_number
                results.append(outcome)
                self.stdout.write(
                    f"ROUND{round_number} case={case.id} {case.case_number or case.name}: "
                    f"{outcome['status']} dur={outcome['duration']:.1f}s record={outcome['record_id']}"
                )
        # Only a passing run can hand back a green report that was secretly warm. A run that failed before
        # it ever produced a plan reports plan_source=unknown, and failing the whole command over that threw
        # away the report for an unrelated planner timeout.
        warm = [
            item for item in results
            if item['status'] == 'passed' and item.get('plan_source') not in {'model', None, ''}
        ]
        passed = sum(1 for item in results if item['status'] == 'passed')
        summary = {
            'rounds': rounds, 'cases': len(cases), 'runs': len(results), 'passed': passed,
            'env_retries': env_retries,
            'plan_sources': Counter(str(item.get('plan_source') or 'unknown') for item in results),
            'results': results,
        }
        self.stdout.write(f'SUMMARY passed={passed}/{len(results)}')
        if options['json']:
            with open(options['json'], 'w', encoding='utf-8') as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        if options['assert_cold'] and warm:
            # A cold run that quietly reused a proven plan measures nothing, and it looks exactly like a real
            # pass. Raised only after the summary and the JSON are written, so the evidence survives.
            detail = ', '.join(f"record={item['record_id']} plan_source={item['plan_source']}" for item in warm[:10])
            raise CommandError(f'声明了冷跑，但 {len(warm)} 次通过的运行复用了已有计划：{detail}')
        if passed != len(results):
            raise CommandError(f'{len(results) - passed} 次运行未通过。')

    def _select_cases(self, options):
        if options['cases']:
            ids = [int(item) for item in str(options['cases']).split(',') if item.strip()]
            by_id = {case.id: case for case in AICase.objects.filter(id__in=ids)}
            return [by_id[case_id] for case_id in ids if case_id in by_id]
        if options['project'] is not None:
            queryset = AICase.objects.filter(project_id=options['project'])
            if options['case_prefix']:
                queryset = queryset.filter(case_number__startswith=options['case_prefix'])
            return list(queryset.order_by('case_number', 'id'))
        raise CommandError('请通过 --cases 或 --project 指定用例。')

    @staticmethod
    def _select_user(username):
        User = get_user_model()
        user = User.objects.filter(username=username).first() if username else User.objects.filter(is_superuser=True).order_by('id').first()
        if user is None:
            raise CommandError('找不到执行人用户。')
        return user

    @staticmethod
    def _select_environment(env_id):
        if env_id is not None:
            environment = EnvironmentConfiguration.objects.filter(id=env_id).first()
            if environment is None:
                raise CommandError(f'环境配置 {env_id} 不存在。')
            return environment
        return EnvironmentConfiguration.objects.filter(is_default=True).order_by('id').first()

    @staticmethod
    def _environment_failure(record_id):
        record = AIExecutionRecord.objects.filter(pk=record_id).only('logs').first()
        return bool(record) and '被测环境不可用' in str(record.logs or '')

    def _run_case(self, case, user, environment, options):
        record = launch_case_execution(
            case,
            user=user,
            execution_mode=options['execution_mode'],
            use_cache=not options['no_cache'],
            environment_configuration=environment,
            force_replan=bool(options.get('force_replan')),
        )
        deadline = time.time() + max(30, int(options['timeout']))
        while time.time() < deadline:
            current = AIExecutionRecord.objects.filter(pk=record.id).values(
                'status', 'duration', 'planner_trace',
            ).first()
            if current and current['status'] in TERMINAL_STATUSES:
                return {'case_id': case.id, 'case_number': case.case_number, 'record_id': record.id, 'status': current['status'], 'duration': float(current['duration'] or 0.0), 'plan_source': self._plan_source(current)}
            time.sleep(max(0.5, float(options['poll'])))
        return {
            'case_id': case.id, 'case_number': case.case_number, 'record_id': record.id,
            'status': 'timeout', 'duration': 0.0, 'plan_source': 'unknown',
        }

    @staticmethod
    def _plan_source(current):
        """Where this run's global plan came from: model (freshly planned), verified, cache or persisted."""
        trace = (current or {}).get('planner_trace')
        if isinstance(trace, str):
            try:
                trace = json.loads(trace)
            except json.JSONDecodeError:
                return 'unknown'
        if not isinstance(trace, dict):
            return 'unknown'
        return str(trace.get('plan_source') or 'unknown')
