"""Publish an isolated output bundle on the latest remote head, without rebase."""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def git(*args, cwd=None, check=True):
    return subprocess.run(['git', *args], cwd=cwd, check=check, text=True, capture_output=True)


def prefer(source, destination):
    if not destination.exists():
        return True
    a, b = json.loads(source.read_text()), json.loads(destination.read_text())
    # A failed attempt must not displace a complete daily/validation snapshot.
    if 'daily' in source.parts or source.name == 'validation.json':
        if bool(a.get('complete')) != bool(b.get('complete')):
            return bool(a.get('complete'))
    return a['started_at'] > b['started_at']


def overlay(bundle, dest):
    # Each run is immutable; overlapping execution cannot remove any earlier run.
    for source in (bundle / 'runs').glob('**/*'):
        if source.is_file():
            target = dest / source.relative_to(bundle)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise RuntimeError('immutable run collision: ' + str(source))
            shutil.copy2(source, target)
    for source in (bundle / 'daily').glob('*.json'):
        target = dest / 'daily' / source.name
        if prefer(source, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            companion = source.with_suffix('.md')
            if companion.exists():
                shutil.copy2(companion, target.with_suffix('.md'))
    for name in ('latest.json', 'validation.json', 'last_schedule.json'):
        source, target = bundle / name, dest / name
        if source.exists() and prefer(source, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if name == 'latest.json':
                for alias in ('latest.md', 'volume.csv', 'surge.csv'):
                    if (bundle / alias).exists():
                        shutil.copy2(bundle / alias, dest / alias)


def publish(bundle):
    bundle = Path(bundle).resolve()
    if not (bundle / 'latest.json').exists():
        raise RuntimeError('No current-run report to persist')
    for attempt in range(5):
        git('fetch', 'origin', 'main')
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp) / 'publish'
            git('worktree', 'add', '--detach', str(checkout), 'origin/main')
            try:
                overlay(bundle, checkout / 'data')
                git('add', 'data', cwd=checkout)
                if git('diff', '--cached', '--quiet', cwd=checkout, check=False).returncode == 0:
                    return
                git('-c', 'user.name=github-actions[bot]', '-c',
                    'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    'commit', '-m', 'Store BTC market results ' + os.getenv('GITHUB_RUN_ID', ''), cwd=checkout)
                result = git('push', 'origin', 'HEAD:refs/heads/main', cwd=checkout, check=False)
                if result.returncode == 0:
                    print('Results persisted successfully')
                    return
                print('Push failed; retrying on fresh remote head', attempt + 1)
            finally:
                git('worktree', 'remove', '--force', str(checkout))
        time.sleep(2 ** attempt)
    raise RuntimeError('Publish failed after 5 attempts; recover the pre-publish artifact')


if __name__ == '__main__':
    publish(os.environ.get('OUTPUT_DIR', 'collection-output'))
