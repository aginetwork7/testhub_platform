from __future__ import annotations

import requests
from django.core.management.base import BaseCommand, CommandError

from apps.api_automation.models import ApiAutomationRun
from apps.api_automation.runner_client import generate_run_report, is_configured


class Command(BaseCommand):
    help = 'Generate one consolidated Allure report for each API automation run.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--run-id', type=int, help='Generate the consolidated report for one run only.')

    def handle(self, *args, **options) -> None:
        if not is_configured():
            raise CommandError('API automation Runner is not configured.')

        runs = ApiAutomationRun.objects.order_by('id')
        if run_id := options.get('run_id'):
            runs = runs.filter(id=run_id)
        if not runs.exists():
            raise CommandError('No matching API automation runs found.')

        generated_count = 0
        for run in runs:
            try:
                report = generate_run_report(run)
            except requests.RequestException as error:
                self.stderr.write(f'Run {run.id}: report generation request failed: {error}')
                continue
            if report.get('status') != 'PASSED':
                self.stderr.write(f"Run {run.id}: {report.get('error', 'no Allure results')}")
                continue

            run.report_path = report['report_path']
            run.save(update_fields=['report_path'])
            generated_count += 1
            self.stdout.write(f"Run {run.id}: {report['report_path']}")

        self.stdout.write(self.style.SUCCESS(f'Generated {generated_count} consolidated Allure report(s).'))