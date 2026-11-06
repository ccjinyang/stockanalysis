import copy
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import chart_service as service


def fixture():
    return {'chart': {'result': [{
        'meta': {'exchangeTimezoneName': 'America/New_York', 'currency': 'USD'},
        'timestamp': [1704205800, 1704292200, 1704378600],
        'indicators': {'quote': [{'open': [100, 102, None], 'high': [104, 106, 107],
                                 'low': [99, 101, 100], 'close': [103, 105, 106],
                                 'volume': [1000, 2000, 3000]}]},
    }], 'error': None}}


class ChartServiceTests(unittest.TestCase):
    def setUp(self):
        service.CACHE.clear()
        service.PE_CACHE.clear()

    def test_symbols_and_ranges(self):
        for ticker in ('amzn', 'BRK-B', 'SHOP.TO', '^GSPC'):
            self.assertEqual(service.validate(ticker, '5y'), ticker.upper())
        for ticker in ('', '../file', 'https://example.com', '<script>', 'A' * 21):
            with self.assertRaises(ValueError):
                service.validate(ticker, '5y')
        with self.assertRaises(ValueError):
            service.validate('AMZN', 'forever')

    def test_normalize_drops_partial_and_invalid_bars(self):
        result = service.normalize(fixture(), 'AMZN')
        self.assertEqual(len(result['bars']), 2)
        self.assertEqual(result['bars'][0]['date'], '2024-01-02')
        self.assertEqual(sum(b['volume'] for b in result['bars']), 3000)
        for bad in (float('nan'), float('inf'), -5):
            payload = copy.deepcopy(fixture())
            payload['chart']['result'][0]['indicators']['quote'][0]['close'][0] = bad
            with self.assertRaises(service.DataUnavailable):
                service.normalize(payload, 'AMZN')

    def test_exchange_date_uses_timezone_not_utc(self):
        payload = fixture()
        payload['chart']['result'][0]['timestamp'][0] = 1704241800  # Jan 3 UTC, Jan 2 in NY
        self.assertEqual(service.normalize(payload, 'AMZN')['bars'][0]['date'], '2024-01-02')

    def test_provider_error(self):
        with self.assertRaises(service.DataUnavailable):
            service.normalize({'chart': {'result': None, 'error': {'code': 'Not Found'}}}, 'X')

    def test_cache_and_expiration(self):
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps(fixture()).encode())
        with patch.object(service, 'urlopen', side_effect=response) as provider:
            first = service.fetch_history('AMZN', '5y')
            second = service.fetch_history('AMZN', '5y')
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertEqual(provider.call_count, 1)
            key = ('AMZN', '5y')
            service.CACHE[key] = (service.time.monotonic() - service.CACHE_SECONDS - 1, service.CACHE[key][1])
            self.assertFalse(service.fetch_history('AMZN', '5y')['cached'])
            self.assertEqual(provider.call_count, 2)

    def test_outage_does_not_become_example_data(self):
        with patch.object(service, 'urlopen', side_effect=URLError('offline')) as provider:
            with self.assertRaisesRegex(service.DataUnavailable, 'Cannot retrieve'):
                service.fetch_history('AMZN', '5y')
            self.assertEqual(provider.call_count, 2)
            self.assertFalse(service.CACHE)

    def test_forward_pe_prefers_monthly_filters_and_sorts(self):
        def point(date, value):
            return {'asOfDate': date, 'reportedValue': {'raw': value}}
        payload = {'timeseries': {'result': [
            {'quarterlyForwardPeRatio': [point('2024-03-31', 22), point('2024-06-30', 25)]},
            {'monthlyForwardPeRatio': [point('2024-06-30', 24), point('2024-05-31', 23),
                                      point('2024-07-31', 0), point('2024-08-31', -5),
                                      point('2024-09-30', float('nan')), point('2024-10-31', True),
                                      point('2024-02-30', 10), point('2024-12-31', 30)]},
        ]}}
        result = service.normalize_forward_pe(payload, 'AMZN', '2024-03-01', '2024-11-01')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([(p['date'], p['value']) for p in result['points']],
                         [('2024-03-31', 22), ('2024-05-31', 23), ('2024-06-30', 24)])
        self.assertEqual(result['points'][-1]['frequency'], 'monthly')

    def test_forward_pe_does_not_substitute_trailing_pe(self):
        payload = {'timeseries': {'result': [{'monthlyPeRatio': [
            {'asOfDate': '2024-03-31', 'reportedValue': {'raw': 20}}]}]}}
        result = service.normalize_forward_pe(payload, 'SOXX', '2024-01-01', '2024-12-31')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['points'], [])
        self.assertIn('No historical', result['message'])

    def test_forward_pe_provider_error_is_not_missing_coverage(self):
        with self.assertRaises(service.DataUnavailable):
            service.normalize_forward_pe({'timeseries': {'error': {'code': 'Unauthorized'}}},
                                         'AMZN', '2024-01-01', '2024-12-31')

    def test_forward_pe_has_own_cache(self):
        payload = {'timeseries': {'result': []}}
        with patch.object(service, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(json.dumps(payload).encode())) as provider:
            self.assertFalse(service.fetch_forward_pe('SOXX', '1y')['cached'])
            self.assertTrue(service.fetch_forward_pe('SOXX', '1y')['cached'])
            self.assertEqual(provider.call_count, 1)
            request = provider.call_args[0][0]
            self.assertIn('monthlyForwardPeRatio', request.full_url)
            self.assertFalse(service.CACHE)
            service.PE_CACHE[('SOXX', '1y')] = (service.time.monotonic() - service.PE_CACHE_SECONDS - 1, {})
            self.assertFalse(service.fetch_forward_pe('SOXX', '1y')['cached'])
            self.assertEqual(provider.call_count, 2)

    def test_forward_pe_outage_is_an_error(self):
        with patch.object(service, 'urlopen', side_effect=URLError('offline')):
            with self.assertRaisesRegex(service.DataUnavailable, 'could not be retrieved'):
                service.fetch_forward_pe('AMZN', '1y')
            self.assertFalse(service.PE_CACHE)


if __name__ == '__main__':
    unittest.main()
