"""Export binding-failure samples: what each unbound assertion wanted, and what the page offered."""

import json

from django.core.management.base import BaseCommand

from apps.ai_testing.models import AIExecutionRecord


class Command(BaseCommand):
    help = '导出绑定失败样本（intent 与当时页面上的候选控件），用于离线分析匹配判据。'

    def add_arguments(self, parser):
        parser.add_argument('--records', default='', help='逗号分隔的执行记录 id；缺省取最近的若干条')
        parser.add_argument('--limit', type=int, default=20, help='缺省模式下回溯的执行记录条数')
        parser.add_argument('--case', default='', help='仅统计该用例名')
        parser.add_argument('--json', default='', help='把样本写入该 JSON 文件')

    def handle(self, *args, **options):
        queryset = AIExecutionRecord.objects.all()
        if options['case']:
            queryset = queryset.filter(case_name=options['case'])
        if options['records']:
            ids = [int(value) for value in options['records'].split(',') if value.strip()]
            queryset = queryset.filter(id__in=ids)
        else:
            queryset = queryset.order_by('-id')[:max(1, options['limit'])]

        samples = []
        for record in queryset:
            for artifact in self._artifacts(record):
                if not isinstance(artifact, dict) or artifact.get('type') != 'binders_declined':
                    continue
                for item in artifact.get('unresolved') or []:
                    samples.append({
                        'record_id': record.id,
                        'case_name': record.case_name,
                        'step': artifact.get('step'),
                        'assert_kind': item.get('assert_kind'),
                        'intent': item.get('intent'),
                        'binders': artifact.get('binders') or [],
                        'candidates': artifact.get('candidates') or [],
                        'media_inventory': artifact.get('media_inventory') or {},
                    })

        self.stdout.write(f'binding failures: {len(samples)}')
        with_candidates = [s for s in samples if s['candidates']]
        self.stdout.write(
            f'带候选控件的样本: {len(with_candidates)}'
            + ('' if with_candidates else '  （旧记录没有这份数据，需重新运行才会采集）')
        )
        for sample in samples[:25]:
            self.stdout.write(
                f"\n  record={sample['record_id']} step={sample['step']} "
                f"{sample['assert_kind']} | {str(sample['intent'])[:90]}"
            )
            if sample['media_inventory']:
                self.stdout.write(f"    媒体: {sample['media_inventory']}")
            for candidate in sample['candidates'][:5]:
                self.stdout.write(
                    f"    候选 命中{candidate.get('matched_tokens')} "
                    f"[{candidate.get('role') or candidate.get('tag')}] {str(candidate.get('name'))[:70]}"
                )
            if not sample['candidates']:
                self.stdout.write('    （无候选控件记录）')

        if options['json']:
            with open(options['json'], 'w', encoding='utf-8') as handle:
                json.dump(samples, handle, ensure_ascii=False, indent=2, default=str)
            self.stdout.write(f'\nwrote {len(samples)} samples -> {options["json"]}')

    @staticmethod
    def _artifacts(record):
        artifacts = record.artifacts
        if isinstance(artifacts, str):
            try:
                artifacts = json.loads(artifacts)
            except json.JSONDecodeError:
                return []
        return artifacts or []
