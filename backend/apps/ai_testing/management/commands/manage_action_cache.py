"""Inspect or clear the database-backed step action cache."""

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from apps.ai_testing.models import AIActionCacheEntry


class Command(BaseCommand):
    help = '查看、清理 AI 步骤动作缓存（ai_testing_action_cache_entries）。'

    def add_arguments(self, parser):
        parser.add_argument('--stats', action='store_true', help='按用例输出条目数、命中数与过期数')
        parser.add_argument('--purge-expired', action='store_true', help='删除已过期条目')
        parser.add_argument('--clear', action='store_true', help='删除条目（可配合 --case / --project 限定范围）')
        parser.add_argument('--case', default='', help='仅作用于该用例名')
        parser.add_argument('--project', type=int, default=None, help='仅作用于该项目 id')

    def handle(self, *args, **options):
        queryset = AIActionCacheEntry.objects.all()
        if options['case']:
            queryset = queryset.filter(case_name=options['case'])
        if options['project'] is not None:
            queryset = queryset.filter(project_id=options['project'])
        now = timezone.now()
        if options['purge_expired']:
            deleted = queryset.filter(expires_at__lte=now).delete()[0]
            self.stdout.write(f'purged expired entries: {deleted}')
        if options['clear']:
            deleted = queryset.delete()[0]
            self.stdout.write(f'cleared entries: {deleted}')
        if options['stats'] or not (options['purge_expired'] or options['clear']):
            total = queryset.count()
            expired = queryset.filter(expires_at__lte=now).count()
            self.stdout.write(f'entries={total} expired={expired}')
            rows = (
                queryset.values('case_name')
                .annotate(entries=Count('id'), hits=Sum('hit_count'), steps=Count('step_index', distinct=True))
                .order_by('-entries')[:50]
            )
            for row in rows:
                self.stdout.write(f"{row['case_name']}: entries={row['entries']} steps={row['steps']} hits={row['hits'] or 0}")
