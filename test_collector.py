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

if __name__ == '__main__': unittest.main()
