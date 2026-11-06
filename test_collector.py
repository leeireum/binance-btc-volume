import unittest
from collector import universe, series, ratio, ranked, DAY

class IntegrityTests(unittest.TestCase):
    def test_universe_filters(self):
        base = dict(symbol='ABTC', quoteAsset='BTC', status='TRADING', isSpotTradingAllowed=True)
        pairs = [base, dict(base, symbol='BBTC', status='BREAK'),
                 dict(base, symbol='CBTC', isSpotTradingAllowed=False),
                 dict(base, symbol='BTCUSDT', quoteAsset='USDT')]
        self.assertEqual(universe({'symbols': pairs}), ['ABTC'])

    def test_gap_and_duplicate_rejected(self):
        def bar(t): return [t, 0, 0, 0, 0, 0, t + DAY - 1, '2']
        self.assertEqual(series([bar(0), bar(DAY)], 0, 2, DAY), [2, 2])
        for bars in ([bar(0)], [bar(0), bar(0)], [bar(0), bar(2 * DAY)]):
            with self.assertRaises(ValueError): series(bars, 0, 2, DAY)

    def test_zero_baseline_and_missing_rank(self):
        self.assertIsNone(ratio(100, 0))
        self.assertEqual(ratio(20, 10), 2)
        rows = [{'symbol': 'A', 'v': None}, {'symbol': 'B', 'v': 0}, {'symbol': 'C', 'v': 2}]
        self.assertEqual([r['symbol'] for r in ranked(rows, 'v')], ['C', 'B'])


class EndToEndTests(unittest.TestCase):
    def test_complete_and_failed_history(self):
        from unittest.mock import patch
        import collector
        anchor = 10 * DAY
        def fake(url, kind='json'):
            from urllib.parse import urlparse, parse_qs
            if '/exchangeInfo' in url:
                return {'symbols': [dict(symbol='ETHBTC', quoteAsset='BTC', status='TRADING', isSpotTradingAllowed=True)]}
            if '/time' in url: return {'serverTime': anchor}
            if '/ticker/24hr' in url:
                return [{'symbol': 'ETHBTC', 'quoteVolume': '14', 'priceChangePercent': '-2', 'openTime': anchor-DAY, 'closeTime': anchor}]
            q = parse_qs(urlparse(url).query)
            step = DAY if q['interval'][0] == '1d' else collector.HOUR
            start, limit = int(q['startTime'][0]), int(q['limit'][0])
            return [[start+i*step, 0, 0, 0, 0, 0, start+(i+1)*step-1, '2'] for i in range(limit)]
        with patch.object(collector, 'request', side_effect=fake), patch.object(collector, 'fallback_probe', return_value=[]), patch.object(collector.time, 'sleep'):
            report = collector.collect()
        self.assertTrue(report['complete'])
        self.assertEqual(report['ticker_count'], 1)
        self.assertEqual(report['rows'][0]['surge_24h'], 7)
        self.assertEqual(report['rows'][0]['surge_1h'], 1)
        self.assertEqual(report['rows'][0]['surge_4h'], 1)
        self.assertEqual(report['rows'][0]['price_change_percent'], -2)
        def gap(url, kind='json'):
            result = fake(url, kind)
            return result[:-1] if 'interval=1d' in url else result
        with patch.object(collector, 'request', side_effect=gap), patch.object(collector, 'fallback_probe', return_value=[]), patch.object(collector.time, 'sleep'):
            report = collector.collect()
        self.assertFalse(report['complete'])
        self.assertEqual(report['ticker_count'], 1)
        self.assertEqual(report['history_count'], 0)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, patch.object(collector, 'OUT', Path(tmp)):
            self.assertFalse(collector.save(report))
            self.assertTrue((Path(tmp) / 'latest.md').exists())
            self.assertIn('ETHBTC', (Path(tmp) / 'surge.csv').read_text())

    def test_unknown_universe_never_zero(self):
        from unittest.mock import patch
        import collector
        with patch.object(collector, 'request', side_effect=RuntimeError('blocked')), patch.object(collector, 'fallback_probe', return_value=[]):
            report = collector.collect()
        self.assertFalse(report['complete'])
        self.assertIsNone(report['expected_count'])

if __name__ == '__main__': unittest.main()
