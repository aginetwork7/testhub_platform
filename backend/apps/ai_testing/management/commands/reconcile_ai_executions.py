"""Mark AI test executions whose worker vanished as failed instead of leaving them 'running'."""

from django.core.management.base import BaseCommand

from apps.ai_testing.execution.dispatch import reconcile_stale_executions


class Command(BaseCommand):
    help = '将心跳超时的 AI 智能测试执行记录标记为失败（默认 30 分钟无心跳）。'

    def add_arguments(self, parser):
        parser.add_argument('--stale-minutes', type=int, default=30, help='无心跳多少分钟后视为进程丢失')

    def handle(self, *args, **options):
        reconciled = reconcile_stale_executions(options['stale_minutes'])
        if reconciled:
            self.stdout.write(self.style.WARNING(f'已标记 {len(reconciled)} 条记录为失败: {reconciled}'))
        else:
            self.stdout.write(self.style.SUCCESS('没有需要对账的执行记录。'))
