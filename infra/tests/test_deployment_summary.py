import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('watch_deployment', ROOT / 'infra/scripts/suivre-deploiement.py')
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class RepositorySelectionTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(folder)
        self.enterContext(patch.object(watch, 'ROOT', self.root))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_persistent_repo_is_used_in_all_deployment_calls(self):
        (self.root / '.env').write_text('SECRET_KEY="unrelated secret"\nGH_REPO="Nyx-Akuma/cafeDolbeau_" # fork\n')
        with patch.object(watch.uuid, 'uuid4', return_value=SimpleNamespace(hex='token')), \
                patch.object(watch.subprocess, 'run', side_effect=[
                    None,
                    SimpleNamespace(stdout=json.dumps([{'databaseId': 123, 'displayTitle': 'Déployer sur EC2 · main · token'}])),
                    SimpleNamespace(returncode=0), SimpleNamespace(stdout=''),
                ]) as run:
            self.assertEqual(watch.main(['--lancer']), 0)
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][-2:], ['--repo', 'Nyx-Akuma/cafeDolbeau_'])
            self.assertEqual(call.kwargs['cwd'], self.root)
            self.assertNotIn('unrelated secret', str(call))

    def test_github_repo_takes_priority_over_legacy_guide_variable(self):
        (self.root / '.env').write_text('GH_REPO=file/fork\n')
        with patch.dict(os.environ, {'GH_REPO': 'explicit/fork', 'CAFE_REPO': 'guide/fork'}):
            self.assertEqual(watch.configured_repo(), 'explicit/fork')
        with patch.dict(os.environ, {'CAFE_REPO': 'guide/fork'}):
            self.assertEqual(watch.configured_repo(), 'file/fork')
        (self.root / '.env').write_text('GH_REPO=\n')
        with patch.dict(os.environ, {'CAFE_REPO': 'guide/fork'}):
            self.assertEqual(watch.configured_repo(), 'guide/fork')

    def test_no_explicit_repo_preserves_cli_default(self):
        for content in [None, 'GH_REPO=\nSECRET_KEY=anything\n']:
            with self.subTest(content=content):
                if content is not None:
                    (self.root / '.env').write_text(content)
                with patch.object(watch.subprocess, 'run') as run:
                    watch.gh('run', 'watch', '123')
                self.assertEqual(run.call_args.args[0], ['gh', 'run', 'watch', '123'])

    def test_export_and_comments_are_supported_without_loading_other_settings(self):
        (self.root / '.env').write_text('SECRET_KEY="not a valid shell string\nexport GH_REPO=owner/fork # comment\n')
        self.assertEqual(watch.configured_repo(), 'owner/fork')
        self.assertNotIn('SECRET_KEY', os.environ)

    def test_invalid_repository_setting_stops_before_github_call(self):
        (self.root / '.env').write_text('GH_REPO=owner/fork extra\n')
        with patch.object(watch.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                watch.main(['--lancer'])
        run.assert_not_called()


class DeploymentSummaryTests(unittest.TestCase):
    def test_launch_waits_for_its_own_run(self):
        title = 'Déployer sur EC2 · feature/test · unique-token'
        with patch.object(watch.uuid, 'uuid4', return_value=SimpleNamespace(hex='unique-token')), \
                patch.object(watch.time, 'sleep') as sleep, \
                patch.object(watch, 'gh', side_effect=[
                    None,
                    SimpleNamespace(stdout=json.dumps([{'databaseId': 1, 'displayTitle': 'another run'}])),
                    SimpleNamespace(stdout=json.dumps([{'databaseId': 1, 'displayTitle': 'another run'},
                                                      {'databaseId': 2, 'displayTitle': title}])),
                    SimpleNamespace(returncode=0), SimpleNamespace(stdout=''),
                ]) as gh:
            self.assertEqual(watch.main(['--lancer', '--ref', 'feature/test']), 0)
        self.assertEqual(gh.call_args_list[0].args, (
            'workflow', 'run', 'deploy.yml', '--ref', 'main', '-f', 'ref=feature/test',
            '-f', 'suivi_id=unique-token'))
        self.assertEqual(gh.call_args_list[3].args, ('run', 'watch', '2', '--exit-status'))
        sleep.assert_called_once_with(2)

    def test_invalid_launch_arguments_do_not_call_github(self):
        for arguments in [['--lancer', '123'], ['--ref', 'feature/test']]:
            with self.subTest(arguments=arguments), patch.object(watch, 'gh') as gh:
                with self.assertRaises(SystemExit):
                    watch.main(arguments)
                gh.assert_not_called()

    def test_failed_dispatch_does_not_watch_previous_run(self):
        with patch.object(watch, 'gh', side_effect=subprocess.CalledProcessError(1, 'gh')) as gh:
            with self.assertRaises(subprocess.CalledProcessError):
                watch.main(['--lancer'])
        gh.assert_called_once()

    def test_dispatch_timeout_does_not_trigger_again(self):
        with patch.object(watch.time, 'monotonic', side_effect=[0, 121]), \
                patch.object(watch, 'gh') as gh:
            with self.assertRaisesRegex(SystemExit, 'Pipeline déclenché'):
                watch.launch('main')
        gh.assert_called_once()

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
