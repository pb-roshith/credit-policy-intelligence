import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from fastapi import HTTPException
from app.services.portfolio_concentration import concentrations


def request(**changes):
    return dict(dict(account_user_id='manager', credit_request_number='CR-1', shared_deal_id=None,
                     industry='Manufacturing', geography='India', exposure=100), **changes)


def deal(**changes):
    return dict(dict(id='deal_1', industry='Technology', geography='USA', amount=300, currency='USD'), **changes)


class ConcentrationTests(unittest.TestCase):
    def test_includes_deals_and_cpi_in_both_charts(self):
        result = concentrations([deal()], [request()], [])
        self.assertEqual([(r['label'], r['exposure_percent']) for r in result['sectors']],
                         [('Technology', Decimal('75.0')), ('Manufacturing', Decimal('25.0'))])
        self.assertEqual([(r['label'], r['exposure_percent']) for r in result['geographies']],
                         [('USA', Decimal('75.0')), ('India', Decimal('25.0'))])

    def test_linked_request_is_not_counted_twice(self):
        result = concentrations([deal(), deal()], [request(shared_deal_id='deal_1')], [])
        self.assertEqual(len(result['sectors']), 1)
        self.assertEqual(result['sectors'][0]['exposure'], 100)
        self.assertEqual(result['sectors'][0]['exposure_percent'], 100)

    def test_currencies_are_separate_without_exchange_rate_assumptions(self):
        result = concentrations([deal(currency='INR', amount=10000)], [request()], [])
        self.assertEqual({r['currency']: r['exposure'] for r in result['sectors']}, {'INR': 10000, 'USD': 100})
        self.assertTrue(all(r['exposure_percent'] == 100 for r in result['sectors']))

    def test_explicit_exposure_takes_precedence_and_zero_is_preserved(self):
        for value in (0, 50):
            result = concentrations([deal(intake={'exposure': value})], [], [])
            self.assertEqual(result['sectors'][0]['exposure'], value)

    def test_missing_linked_exposure_falls_back_to_deal_amount(self):
        result = concentrations([deal()], [request(shared_deal_id='deal_1', exposure=None)], [])
        self.assertEqual(result['sectors'][0]['exposure'], 300)

    def test_open_exceptions_map_to_deals_and_account_scoped_local_ids(self):
        exceptions = [dict(account_user_id='manager', request_id='CR-1', count=2),
                      dict(account_user_id='other', request_id='CR-1', count=3),
                      dict(account_user_id='manager', request_id='deal_1', count=1)]
        result = concentrations([deal()], [request(shared_deal_id='deal_1'),
            request(account_user_id='other', industry='Agriculture')], exceptions)
        self.assertEqual({r['label']: r['breaches'] for r in result['sectors']},
                         {'Technology': 3, 'Agriculture': 3})

    def test_invalid_values_are_not_aggregated_and_zero_totals_are_safe(self):
        result = concentrations([deal(amount='NaN'), deal(id='deal_2', currency='', amount=5)],
                                [request(exposure=0)], [])
        self.assertEqual(len(result['sectors']), 1)
        self.assertEqual(result['sectors'][0]['exposure_percent'], 0)

    def test_deal_service_unavailable_keeps_linked_cpi_requests(self):
        result = concentrations([], [request(shared_deal_id='deal_1')], [])
        self.assertEqual(result['sectors'][0]['exposure'], 100)


class PortfolioRouteTests(unittest.TestCase):
    def test_route_uses_authorized_deals_and_reports_source_unavailability(self):
        from app.routers.dashboard import portfolio
        user = {'user_id': 'analyst', 'role': 'credit_analyst'}
        for unavailable in (False, True):
            with self.subTest(unavailable=unavailable):
                connection = MagicMock()
                def execute(query, *args):
                    result = MagicMock()
                    result.fetchall.return_value = [request()] if 'FROM credit_requests cr' in query else []
                    result.fetchone.return_value = {'value': '2026-10-24'}
                    return result
                connection.execute.side_effect = execute
                with patch('app.routers.dashboard.db_connection') as db, \
                     patch('app.routers.dashboard.call_shared_deals') as shared:
                    db.return_value.__enter__.return_value = connection
                    if unavailable:
                        shared.side_effect = HTTPException(503, 'Unavailable')
                    else:
                        shared.return_value = [deal()]
                    result = portfolio(user)
                    shared.assert_called_once_with(user)
                self.assertEqual(len(result['sectors']), 1 if unavailable else 2)
                self.assertEqual(bool(result['source_warning']), unavailable)
