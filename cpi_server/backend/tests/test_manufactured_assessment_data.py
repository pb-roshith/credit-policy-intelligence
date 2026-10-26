import unittest
from app.manufacture_data.assessment_data import sample_financials


class SampleFinancialTests(unittest.TestCase):
    def test_financial_ratios_correspond_to_stored_underlying_values(self):
        data=sample_financials(10_000_000,20_000_000)
        self.assertEqual(data['total_debt'],30_000_000)
        self.assertAlmostEqual(data['total_debt']/data['ebitda'],data['leverage_ratio'],places=6)
        self.assertAlmostEqual(data['net_operating_income']/data['annual_debt_service'],data['dscr'],places=6)
        self.assertAlmostEqual(100*data['total_debt']/data['collateral_value'],data['ltv'],places=6)
