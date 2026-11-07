import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collector
from persist_results import git, publish


def bundle(path, stamp, event='workflow_dispatch', complete=True):
    path.mkdir(parents=True, exist_ok=True)
    data = dict(started_at=stamp, complete=complete)
    (path / 'latest.json').write_text(json.dumps(data))
    runs = path / 'runs' / stamp.replace(':', '')
    runs.mkdir(parents=True)
    (runs / 'report.json').write_text(json.dumps(data))
    daily = path / 'daily'
    daily.mkdir()
    (daily / '2026-11-07.json').write_text(json.dumps(data))


class PublicationTests(unittest.TestCase):
    def test_remote_update_and_rejected_push_keep_both_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, worker, writer = [root / n for n in ('remote.git', 'worker', 'writer')]
            git('init', '--bare', str(remote))
            git('clone', str(remote), str(worker))
            git('config', 'user.name', 'test', cwd=worker)
            git('config', 'user.email', 'test@example.test', cwd=worker)
            (worker / 'README').write_text('preserve me')
            git('add', '.', cwd=worker)
            git('commit', '-m', 'initial', cwd=worker)
            git('branch', '-M', 'main', cwd=worker)
            git('push', 'origin', 'main', cwd=worker)
            git('clone', '-b', 'main', str(remote), str(writer))
            git('config', 'user.name', 'test', cwd=writer)
            git('config', 'user.email', 'test@example.test', cwd=writer)
            old, new = root / 'old', root / 'new'
            bundle(old, '2026-11-07T00:00:00+00:00')
            bundle(new, '2026-11-07T01:00:00+00:00')
            import persist_results
            original = persist_results.git
            raced = False
            def race(*args, **kwargs):
                nonlocal raced
                if args[:2] == ('push', 'origin') and not raced:
                    raced = True
                    from persist_results import overlay
                    overlay(new, writer / 'data')
                    (writer / 'README').write_text('concurrent code edit')
                    original('add', '.', cwd=writer)
                    original('commit', '-m', 'concurrent results and code', cwd=writer)
                    original('push', 'origin', 'main', cwd=writer)
                return original(*args, **kwargs)
            previous = Path.cwd()
            try:
                os.chdir(worker)
                with patch.object(persist_results, 'git', side_effect=race), patch.object(persist_results.time, 'sleep'):
                    publish(old)
                git('fetch', 'origin', 'main')
                latest = json.loads(git('show', 'origin/main:data/latest.json').stdout)
                self.assertEqual(latest['started_at'], '2026-11-07T01:00:00+00:00')
                names = git('ls-tree', '-r', '--name-only', 'origin/main').stdout
                self.assertEqual(names.count('/report.json'), 2)
                self.assertEqual(git('show', 'origin/main:README').stdout, 'concurrent code edit')
                self.assertTrue(raced)
            finally:
                os.chdir(previous)

    def test_late_manual_daily_preserves_actual_time_and_schema(self):
        report = dict(started_at='2026-11-07T00:16:00+00:00', finished_at='2026-11-07T00:17:00+00:00', complete=True,
                      expected_count=26, ticker_count=26, history_count=26, short_term_count=26,
                      rows=[], failures=[], time_note='UTC baseline', top_volume=[], top_surge=[], top_1h=[], top_4h=[])
        with tempfile.TemporaryDirectory() as tmp, patch.object(collector, 'OUT', Path(tmp)), patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch'}):
            collector.save(report)
            d = json.loads((Path(tmp) / 'daily/2026-11-07.json').read_text())
            self.assertEqual(d['started_at'], report['started_at'])
            self.assertTrue(d['execution']['manual'])
            self.assertEqual(d['execution']['actual_started_at_kst'], '2026-11-07T09:16:00+09:00')
            self.assertIsNone(d['execution']['nominal_schedule_at_kst'])
            self.assertFalse((Path(tmp) / 'last_schedule.json').exists())

if __name__ == '__main__': unittest.main()
