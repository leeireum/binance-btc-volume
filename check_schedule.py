"""Read-only verification. Run at/after 07:40 KST with gh authentication."""
import json
import subprocess
from datetime import datetime, timedelta, timezone

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/leeireum/binance-btc-volume/' + path], text=True))

def main():
    local = datetime.now(timezone(timedelta(hours=9)))
    due = local.replace(hour=7, minute=20, second=0, microsecond=0)
    if local < due:
        due -= timedelta(days=1)
    state = api('actions/workflows/collect.yml')['state']
    runs = api('actions/workflows/collect.yml/runs?event=schedule&per_page=100')['workflow_runs']
    matches = [r for r in runs if datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')) >= due]
    result = {'workflow_state': state, 'checked_at_kst': local.isoformat(), 'expected_at_kst': due.isoformat(),
              'deadline_at_kst': (due + timedelta(minutes=20)).isoformat(), 'status': 'waiting', 'runs': [
                  {k: r[k] for k in ('id', 'event', 'status', 'conclusion', 'created_at', 'run_attempt', 'html_url')} for r in matches]}
    if matches:
        r = matches[0]
        result['status'] = 'success' if r['conclusion'] == 'success' else r['conclusion'] or r['status']
        result['created_delay_seconds'] = (datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')) - due).total_seconds()
    elif local >= due + timedelta(minutes=20):
        result['status'] = 'missing_or_delayed'
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'success' and state == 'active' else 2

if __name__ == '__main__': raise SystemExit(main())
