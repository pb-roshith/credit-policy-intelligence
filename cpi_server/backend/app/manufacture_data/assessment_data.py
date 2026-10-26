"""Illustrative financials for manufactured requests, stored before assessment."""
def sample_financials(requested_amount, exposure):
    debt=float(exposure)+float(requested_amount)
    ebitda=round(debt/3.5,2)
    debt_service=round(ebitda/1.6,2)
    return {'total_debt':debt,'ebitda':ebitda,'annual_debt_service':debt_service,
            'debt_service':debt_service,'net_operating_income':ebitda,
            'leverage_ratio':3.5,'dscr':1.6,'debt_service_coverage_ratio':1.6,
            'ltv':65.0,'loan_to_value':65.0,'collateral_value':round(debt/0.65,2)}
