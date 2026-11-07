"""Public Binance BTC spot data only. No exchange credentials required."""
import csv
import io
import json
import os
import time
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal

DAY = 86400000
HOUR = 3600000
BASES = ['https://api.binance.com', 'https://data-api.binance.vision']
OUT = Path(os.getenv('OUTPUT_DIR', 'data'))
EVENTS = []


def now():
    return datetime.now(timezone.utc).isoformat()


def request(url, kind='json'):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'btc-volume-collector/1.0'})
            with urllib.request.urlopen(req, timeout=25) as response:
                body = response.read()
            result = json.loads(body) if kind == 'json' else body
            EVENTS.append({'url': url, 'queried_at': now(), 'attempt': attempt + 1, 'ok': True})
            return result
        except Exception as exc:
            code = getattr(exc, 'code', None)
            EVENTS.append({'url': url, 'queried_at': now(), 'attempt': attempt + 1, 'ok': False,
                           'error_type': type(exc).__name__, 'http_status': code})
            if code in (400, 401, 403, 404, 418, 451):
                break
            delay = min(60, int(exc.headers.get('Retry-After', 2 ** attempt))) if code == 429 else 2 ** attempt
            time.sleep(delay)
    raise RuntimeError('request_failed: ' + url)


def universe(info):
    return sorted(s['symbol'] for s in info['symbols']
                  if s['quoteAsset'] == 'BTC' and s['status'] == 'TRADING'
                  and s.get('isSpotTradingAllowed') is True)


def number(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError('invalid volume')
    return float(n)


def series(candles, start, count, step):
    wanted = list(range(start, start + count * step, step))
    if len(candles) != count or [int(c[0]) for c in candles] != wanted:
        raise ValueError('missing_or_duplicate_candle')
    if any(int(c[6]) != int(c[0]) + step - 1 for c in candles):
        raise ValueError('invalid_candle_close')
    return [number(c[7]) for c in candles]


def ratio(value, mean):
    return value / mean if mean > 0 else None


def fallback_probe(anchor):
    # Diagnostic evidence only: these sources cannot certify today's active universe.
    day = datetime.fromtimestamp((anchor - 2 * DAY) / 1000, timezone.utc).strftime('%Y-%m-%d')
    results = []
    url = f'https://data.binance.vision/data/spot/daily/klines/ETHBTC/1d/ETHBTC-1d-{day}.zip'
    try:
        body = request(url, 'bytes')
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
        number(rows[0][7])
        results.append({'source': url, 'usable_sample': True, 'rows': len(rows), 'complete': False})
    except Exception:
        results.append({'source': url, 'usable_sample': False, 'complete': False})
    url = 'https://api.coingecko.com/api/v3/exchanges/binance/tickers?page=1'
    try:
        ticks = request(url)['tickers']
        results.append({'source': url, 'usable_sample': True,
                        'btc_pairs_page1': sum(t['target'] == 'BTC' for t in ticks), 'complete': False})
    except Exception:
        results.append({'source': url, 'usable_sample': False, 'complete': False})
    url = 'https://coinmarketcap.com/exchanges/binance/'
    try:
        body = request(url, 'bytes')
        results.append({'source': url, 'html_accessible': bool(body),
                        'usable_sample': False, 'complete': False,
                        'note': 'HTML access alone does not verify pair data; no supported parser'})
    except Exception:
        results.append({'source': url, 'usable_sample': False, 'complete': False})
    return results


def ranked(rows, field):
    return sorted((r for r in rows if r.get(field) is not None), key=lambda r: (-r[field], r['symbol']))


def collect():
    started = now()
    report = {'started_at': started, 'expected_count': None, 'ticker_count': 0,
              'history_count': 0, 'short_term_count': 0, 'complete': False, 'rows': [], 'failures': [],
              'time_note': '24h is ticker rolling window. Baseline is last 7 completed UTC days; windows differ and may overlap. 1h/4h use completed hourly candles, excluding the current partial hour.',
              'low_liquidity_btc_threshold': float(os.getenv('MIN_BTC', '1'))}
    base = None
    for candidate in BASES:
        try:
            info = request(candidate + '/api/v3/exchangeInfo')
            expected = universe(info)
            if not expected:
                raise ValueError('empty universe')
            base = candidate
            break
        except Exception:
            continue
    anchor = int(time.time() * 1000)
    if base:
        report.update(source=base, expected_count=len(expected), expected_symbols=expected)
        try:
            anchor = int(request(base + '/api/v3/time')['serverTime'])
            all_tickers = request(base + '/api/v3/ticker/24hr')
            tickers = {}
            for t in all_tickers:
                if t['symbol'] in tickers:
                    raise ValueError('duplicate ticker')
                tickers[t['symbol']] = t
        except Exception:
            tickers = {}
            report['failures'].append({'stage': 'ticker_batch_or_server_time'})
        day_end = anchor // DAY * DAY
        hour_end = anchor // HOUR * HOUR
        report['baseline_start_ms'] = day_end - 7 * DAY
        report['baseline_end_ms'] = day_end
        for symbol in expected:
            row = {'symbol': symbol, 'quote_volume_btc': None, 'price_change_percent': None,
                   'daily_mean_btc': None, 'surge_24h': None, 'surge_1h': None, 'surge_4h': None}
            try:
                t = tickers.get(symbol) or request(base + '/api/v3/ticker/24hr?symbol=' + symbol)
                if t['symbol'] != symbol or abs(int(t['closeTime']) - anchor) > 10 * 60000:
                    raise ValueError('stale_or_mismatched_ticker')
                volume = number(t['quoteVolume'])
                price = float(t['priceChangePercent'])
                if not Decimal(str(price)).is_finite():
                    raise ValueError('invalid price')
                row.update(quote_volume_btc=volume, price_change_percent=price,
                           ticker_open_ms=t['openTime'], ticker_close_ms=t['closeTime'],
                           low_liquidity=volume < report['low_liquidity_btc_threshold'])
                report['ticker_count'] += 1
            except Exception:
                report['failures'].append({'symbol': symbol, 'stage': 'ticker'})
            try:
                url = f'{base}/api/v3/klines?symbol={symbol}&interval=1d&startTime={day_end-7*DAY}&endTime={day_end-1}&limit=7'
                candles = request(url)
                values = series(candles, day_end - 7 * DAY, 7, DAY)
                mean = sum(values) / 7
                row.update(daily_mean_btc=mean, daily_quote_volumes_btc=values)
                if row['quote_volume_btc'] is not None:
                    row['surge_24h'] = ratio(row['quote_volume_btc'], mean)
                report['history_count'] += 1
            except Exception:
                report['failures'].append({'symbol': symbol, 'stage': '7d_history', 'note': 'request failure or insufficient complete candles'})
            try:
                start = hour_end - 172 * HOUR
                candles = request(f'{base}/api/v3/klines?symbol={symbol}&interval=1h&startTime={start}&endTime={hour_end-1}&limit=172')
                v = series(candles, start, 172, HOUR)
                row.update(surge_1h=ratio(v[-1], sum(v[-169:-1])/168),
                           surge_4h=ratio(sum(v[-4:]), sum(v[:-4])/42),
                           volume_1h_btc=v[-1], volume_4h_btc=sum(v[-4:]), short_end_ms=hour_end)
                report['short_term_count'] += 1
            except Exception:
                report['failures'].append({'symbol': symbol, 'stage': 'short_history'})
            report['rows'].append(row)
            time.sleep(0.15)
        try:
            final_symbols = universe(request(base + '/api/v3/exchangeInfo'))
            report['universe_stable'] = final_symbols == expected
            report['universe_added'] = sorted(set(final_symbols) - set(expected))
            report['universe_removed'] = sorted(set(expected) - set(final_symbols))
        except Exception:
            report['universe_stable'] = False
        report['missing_tickers'] = [r['symbol'] for r in report['rows'] if r['quote_volume_btc'] is None]
        report['missing_count'] = len(report['missing_tickers'])
        report['complete'] = (report['universe_stable'] and report['ticker_count'] == len(expected)
                              and report['history_count'] == len(expected))
    else:
        report['failures'].append({'stage': 'universe', 'note': 'current pair count unknown, never zero'})
    # Always test alternatives during validation; on scheduled failures test them again.
    if os.getenv('VALIDATE', 'true') == 'true' or not report['complete']:
        report['fallback_probes'] = fallback_probe(anchor)
    report['finished_at'] = now()
    report['requests'] = EVENTS
    report['volume_ranking'] = ranked(report['rows'], 'quote_volume_btc')
    report['surge_ranking'] = ranked(report['rows'], 'surge_24h')
    report['top_volume'] = report['volume_ranking'][:20]
    report['top_surge'] = ranked(report['rows'], 'surge_24h')[:20]
    report['top_1h'] = ranked(report['rows'], 'surge_1h')[:20]
    report['top_4h'] = ranked(report['rows'], 'surge_4h')[:20]
    return report


def save(report):
    OUT.mkdir(parents=True, exist_ok=True)
    local = datetime.fromisoformat(report['started_at']).astimezone(timezone(timedelta(hours=9)))
    expected = local.replace(hour=7, minute=20, second=0, microsecond=0)
    if local < expected:
        expected -= timedelta(days=1)
    event = os.getenv('GITHUB_EVENT_NAME', 'local')
    report['execution'] = {
        'event': event, 'manual': event == 'workflow_dispatch',
        'run_id': os.getenv('GITHUB_RUN_ID'), 'run_attempt': os.getenv('GITHUB_RUN_ATTEMPT'),
        'run_url': ('https://github.com/' + os.getenv('GITHUB_REPOSITORY', '') + '/actions/runs/' + os.getenv('GITHUB_RUN_ID', '')) if os.getenv('GITHUB_RUN_ID') else None,
        'workflow_created_at': os.getenv('WORKFLOW_CREATED_AT'),
        'actual_started_at_kst': local.isoformat(),
        'nominal_schedule_at_kst': expected.isoformat() if event == 'schedule' else None,
        'schedule_delay_seconds': (local - expected).total_seconds() if event == 'schedule' else None,
        'note': 'Nominal schedule inferred as latest 07:20 KST before collection; not a GitHub guaranteed trigger timestamp.'
    }
    report['collection_date_kst'] = local.date().isoformat()
    stamp = report['started_at'].replace(':', '').replace('+', '_')
    if os.getenv('GITHUB_RUN_ID'):
        stamp += '-' + os.environ['GITHUB_RUN_ID'] + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    path = OUT / 'runs' / stamp
    path.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    (path / 'report.json').write_text(text)
    (OUT / 'latest.json').write_text(text)
    fields = ['rank', 'symbol', 'quote_volume_btc', 'price_change_percent', 'daily_mean_btc',
              'surge_24h', 'surge_1h', 'surge_4h', 'low_liquidity']
    for name, key in [('volume', 'quote_volume_btc'), ('surge', 'surge_24h')]:
        ordered = ranked(report['rows'], key)
        missing = [r for r in report['rows'] if r.get(key) is None]
        with (path / f'{name}.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            for i, row in enumerate(ordered, 1):
                w.writerow(dict(row, rank=i))
            for row in missing:
                w.writerow(dict(row, rank=''))
    for name in ('volume', 'surge'):
        (OUT / f'{name}.csv').write_text((path / f'{name}.csv').read_text())
    lines = [f"# BTC 마켓 거래량 보고서 — {report['started_at']}",
             f"전수 검증: {report['complete']} / 전체: {report['expected_count']} / 수집: {report['ticker_count']} / 7일 이력: {report['history_count']}",
             report['time_note'],
             '실행 정보: ' + json.dumps(report['execution'], ensure_ascii=False)]
    for title, key in [('24시간 거래대금 상위 20', 'top_volume'), ('24시간 급증 상위 20', 'top_surge'), ('1시간 급증', 'top_1h'), ('4시간 급증', 'top_4h')]:
        lines.extend(['', '## ' + title, '', '| 종목 | 24h BTC | 가격변동 % | 24h 배수 | 1h 배수 | 4h 배수 | 저유동성 |', '|---|---:|---:|---:|---:|---:|---|'])
        for row in report[key]:
            cells = [row.get(k) for k in ('symbol', 'quote_volume_btc', 'price_change_percent', 'surge_24h', 'surge_1h', 'surge_4h', 'low_liquidity')]
            lines.append('| ' + ' | '.join('—' if v is None else f'{v:.4f}' if isinstance(v, float) else str(v) for v in cells) + ' |')
    lines.extend(['', '## 실패 항목', '', '```json', json.dumps(report['failures'], ensure_ascii=False, indent=2), '```', '', '요청별 출처와 조회 시각은 report.json의 requests에 기록됩니다.'])
    markdown = '\n'.join(lines) + '\n'
    (path / 'report.md').write_text(markdown)
    (OUT / 'latest.md').write_text(markdown)
    daily = OUT / 'daily'
    daily.mkdir(exist_ok=True)
    (daily / f'{local:%Y-%m-%d}.json').write_text(text)
    (daily / f'{local:%Y-%m-%d}.md').write_text(markdown)
    if event == 'schedule':
        (OUT / 'last_schedule.json').write_text(text)
    summary = (f"complete={report['complete']} expected={report['expected_count']} "
               f"tickers={report['ticker_count']} history={report['history_count']} "
               f"short={report['short_term_count']}\n")
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(summary + '\n' + report['time_note'] + '\n')
    return report['complete']


if __name__ == '__main__':
    raise SystemExit(0 if save(collect()) else 2)

