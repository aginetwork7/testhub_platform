from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.api_automation.executor import _finalize_run, _selected_cases, _update_run_progress
from apps.api_automation.models import ApiAutomationRun


class Command(BaseCommand):
    help = 'Recalculate API automation run counts from stored JUnit artifacts.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--run-id', type=int, help='Recalculate one run only.')

    def handle(self, *args, **options) -> None:
        runs = ApiAutomationRun.objects.order_by('id')
        if run_id := options.get('run_id'):
            runs = runs.filter(id=run_id)
        if not runs.exists():
            raise CommandError('No matching API automation runs found.')

        for run in runs:
            updated_results = self._update_result_counts(run)
            cases = list(_selected_cases(run))
            if run.status in {'PENDING', 'RUNNING'}:
                _update_run_progress(run, cases, include_remaining=True)
            else:
                _finalize_run(run, cases=cases)
            self.stdout.write(f'Run {run.id}: updated {updated_results} JUnit result count(s).')

    def _update_result_counts(self, run: ApiAutomationRun) -> int:
        artifact_root = (Path(settings.MEDIA_ROOT) / 'api-automation').resolve()
        updated_results = 0
        for result in run.case_results.all():
            junit_path = (result.details.get('artifacts') or {}).get('junit')
            if not junit_path:
                continue
            path = (artifact_root / junit_path).resolve()
            if artifact_root not in path.parents or not path.is_file():
                continue
            counts = self._read_junit_counts(path)
            result.details['test_counts'] = counts
            result.save(update_fields=['details'])
            updated_results += 1
        return updated_results

    @staticmethod
    def _read_junit_counts(path: Path) -> dict[str, int]:
        try:
            root = ElementTree.parse(path).getroot()
        except ElementTree.ParseError:
            return {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
        test_cases = root.findall('.//testcase')
        skipped = sum(test_case.find('skipped') is not None for test_case in test_cases)
        failed = sum(
            test_case.find('failure') is not None or test_case.find('error') is not None
            for test_case in test_cases
        )
        total = len(test_cases)
        return {'total': total, 'passed': total - failed - skipped, 'failed': failed, 'skipped': skipped}