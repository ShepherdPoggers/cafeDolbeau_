import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('watch_deployment', ROOT / 'infra/scripts/suivre-deploiement.py')
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class DeploymentSummaryTests(unittest.TestCase):
    def test_extracts_output_without_commands_or_other_steps(self):
        log = '\n'.join([
            'deploy\tDNS EC2 : ec2-example\t2026-11-20T20:00:00Z print(command)',
            'deploy\tDNS EC2 : ec2-example\t2026-11-20T20:00:01.123Z DNS public EC2 : ec2-example',
            'deploy\tDNS EC2 : ec2-example\t2026-11-20T20:00:02Z python3 infra/scripts/transferer-postgres.py --host ubuntu@ec2-example',
            'deploy\tAutre étape\t2026-11-20T20:00:03Z EC2 : unrelated',
        ])
        self.assertEqual(watch.summary_lines(log), [
            'DNS public EC2 : ec2-example',
            'python3 infra/scripts/transferer-postgres.py --host ubuntu@ec2-example',
        ])

    def test_latest_run_is_used_for_watch_and_logs(self):
        with patch.object(watch, 'gh', side_effect=[
            SimpleNamespace(stdout='[{"databaseId": 123}]'),
            SimpleNamespace(returncode=0), SimpleNamespace(stdout=''),
        ]) as gh:
            self.assertEqual(watch.main([]), 0)
        self.assertIn('--branch', gh.call_args_list[0].args)
        self.assertEqual(gh.call_args_list[1].args, ('run', 'watch', '123', '--exit-status'))
        self.assertEqual(gh.call_args_list[2].args, ('run', 'view', '123', '--log'))

    def test_explicit_run_retains_failure_status(self):
        with patch.object(watch, 'gh', side_effect=[
            SimpleNamespace(returncode=1), SimpleNamespace(stdout=''),
        ]) as gh:
            self.assertEqual(watch.main(['456']), 1)
        self.assertEqual(gh.call_count, 2)


if __name__ == '__main__':
    unittest.main()
