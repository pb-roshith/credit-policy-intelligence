"""Concentrations across authorized CPI requests and Dossier deals, by currency."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def _amount(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def concentrations(deals, requests, exceptions):
    counts = defaultdict(int)
    shared_counts = defaultdict(int)
    for row in exceptions:
        counts[(row['account_user_id'], row['request_id'])] += row['count']
        if not row['request_id'].startswith('CR-'):
            shared_counts[row['request_id']] += row['count']
    linked = defaultdict(list)
    for row in requests:
        if row.get('shared_deal_id'):
            linked[row['shared_deal_id']].append(row)
    records = []
    seen = set()
    for deal in deals:
        if deal['id'] in seen:
            continue
        seen.add(deal['id'])
        local = linked.get(deal['id'], [])
        fallback = local[0] if local else {}
        intake = deal.get('intake') or {}
        currency = str(deal.get('currency') or '').strip().upper()
        exposure = deal.get('exposure')
        if exposure is None:
            exposure = intake.get('exposure')
        if exposure is None and currency == 'USD' and local:
            available = [_amount(r.get('exposure')) for r in local]
            exposure = max((value for value in available if value is not None), default=None)
        if exposure is None:
            exposure = deal.get('amount')
        records.append(dict(industry=deal.get('industry') or fallback.get('industry') or 'Unknown',
            geography=deal.get('geography') or fallback.get('geography') or 'Unknown',
            currency=currency, exposure=exposure,
            risk=deal.get('geography_risk') or intake.get('geography_risk') or fallback.get('geography_risk') or 'Unknown',
            breaches=shared_counts[deal['id']] + sum(counts[(r['account_user_id'], r['credit_request_number'])] for r in local)))
    for row in requests:
        if row.get('shared_deal_id') in seen:
            continue
        records.append(dict(industry=row.get('industry') or 'Unknown', geography=row.get('geography') or 'Unknown',
            currency='USD', exposure=row.get('exposure'), risk=row.get('geography_risk') or 'Unknown',
            breaches=counts[(row['account_user_id'], row['credit_request_number'])]))
    totals = defaultdict(Decimal)
    groups = {'sectors': {}, 'geographies': {}}
    for row in records:
        amount = _amount(row['exposure'])
        if amount is None or not row['currency']:
            continue
        currency = row['currency']
        totals[currency] += amount
        for name, field in (('sectors', 'industry'), ('geographies', 'geography')):
            key = (currency, row[field])
            group = groups[name].setdefault(key, dict(label=row[field], currency=currency,
                exposure=Decimal(0), breaches=0, risk='Unknown'))
            group['exposure'] += amount
            group['breaches'] += row['breaches']
            # Preserve the existing chart's risk metadata aggregation.
            if row['risk'] != 'Unknown':
                group['risk'] = max(group['risk'] if group['risk'] != 'Unknown' else '', row['risk'])
    for name, values in groups.items():
        for group in values.values():
            total = totals[group['currency']]
            group['exposure_percent'] = round(group['exposure'] * 100 / total, 1) if total else Decimal(0)
        groups[name] = sorted(values.values(), key=lambda r: (r['currency'], -r['exposure'], r['label']))
    return groups
