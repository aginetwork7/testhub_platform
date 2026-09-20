"""Inspect, clear, export or import the proven execution plans."""

import json
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.ai_testing.execution.verified_plan_persistence import (
    backfill_from_execution_records,
    export_verified_plans,
    import_verified_plans,
)
from apps.ai_testing.models import AIVerifiedPlan


class Command(BaseCommand):
    help = '查看、清理、导出或导入 AI 已验证执行计划（ai_testing_verified_plans）。'

    def add_arguments(self, parser):
        parser.add_argument('--stats', action='store_true', help='按用例输出计划数与验证次数')
        parser.add_argument('--backfill', action='store_true', help='从已通过的执行记录回填计划（可重复执行）')
        parser.add_argument('--clear', action='store_true', help='删除计划（可配合 --case / --case-id / --env 限定范围）')
        parser.add_argument('--export', default='', help='导出为 JSON 文件；传 - 输出到标准输出')
        parser.add_argument('--import', dest='import_path', default='', help='从 JSON 文件导入；传 - 从标准输入读取')
        parser.add_argument('--case', default='', help='仅作用于该用例名')
        parser.add_argument('--case-id', type=int, default=None, help='仅作用于该用例 id')
        parser.add_argument('--env', type=int, default=None, help='仅作用于该运行环境 id')
        parser.add_argument(
            '--target-env', type=int, default=None,
            help='导入时把计划改挂到该运行环境 id（用于把已跑热的环境迁移到新环境）',
        )

    def handle(self, *args, **options):
        queryset = AIVerifiedPlan.objects.all()
        if options['case']:
            queryset = queryset.filter(case_name=options['case'])
        if options['case_id'] is not None:
            queryset = queryset.filter(ai_case_id=options['case_id'])
        if options['env'] is not None:
            queryset = queryset.filter(environment_configuration_id=options['env'])

        if options['backfill']:
            recorded = backfill_from_execution_records(environment_configuration_id=options['env'])
            self.stdout.write(f'backfilled plans: {recorded}')
            return

        if options['import_path']:
            payload = self._read_payload(options['import_path'])
            written = import_verified_plans(payload, environment_configuration_id=options['target_env'])
            self.stdout.write(f'imported plans: {written}')
            return

        if options['export']:
            payload = export_verified_plans(
                ai_case_id=options['case_id'],
                environment_configuration_id=options['env'],
            )
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if options['export'] == '-':
                self.stdout.write(text)
            else:
                with open(options['export'], 'w', encoding='utf-8') as handle:
                    handle.write(text)
                self.stdout.write(f'exported plans: {len(payload)} -> {options["export"]}')
            return

        if options['clear']:
            deleted = queryset.delete()[0]
            self.stdout.write(f'cleared plans: {deleted}')
            return

        total = queryset.count()
        self.stdout.write(f'plans={total}')
        for row in queryset.order_by('-verified_count', '-last_verified_at')[:50]:
            self.stdout.write(
                f'  case={row.case_name or row.ai_case_id or "-"} env={row.environment_configuration_id} '
                f'verified={row.verified_count} last_record={row.last_passed_record_id} '
                f'fingerprint={row.context_fingerprint[:12] or "-"} steps={len(row.plan.get("steps") or [])}'
            )

    @staticmethod
    def _read_payload(path: str):
        raw = sys.stdin.read() if path == '-' else open(path, encoding='utf-8').read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CommandError(f'导入文件不是合法 JSON：{error}') from error
        if not isinstance(payload, list):
            raise CommandError('导入文件应当是一个 JSON 数组。')
        return payload
