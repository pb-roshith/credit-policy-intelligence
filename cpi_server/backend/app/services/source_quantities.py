"""Lossless restoration of explicitly quoted currency amounts; no FX or inference."""
from decimal import Decimal
import re

CURRENCIES=r'USD|INR|EUR|GBP|JPY|CAD|AUD|CHF|CNY|AED|SGD|HKD'
NUMBER=r'[-+]?\d[\d,]*(?:\.\d+)?'
AMOUNT=re.compile(r'\b(?P<currency>'+CURRENCIES+r')\s+(?P<number>'+NUMBER+r')\s+(?P<scale>thousand|million|billion)s?\b',re.I)
AMOUNT_RANGE=re.compile(r'\b(?P<currency>'+CURRENCIES+r')\s+(?P<lower>'+NUMBER+r')\s*(?:(?P<lower_scale>thousand|million|billion)s?\s*)?(?:to|and|[-\u2013\u2014])\s*(?:(?P<upper_currency>'+CURRENCIES+r')\s+)?(?P<upper>'+NUMBER+r')\s+(?P<upper_scale>thousand|million|billion)s?\b',re.I)
SCALES={'thousand':Decimal(1000),'million':Decimal(1000000),'billion':Decimal(1000000000)}


def numeric_fields(rule):
    for name in ('threshold_value','lower_bound','upper_bound'):
        value=getattr(rule,name)
        for index,item in enumerate(value if isinstance(value,list) else [value]):
            if isinstance(item,(int,float)) and not isinstance(item,bool):
                yield name,index,item


def quoted_amounts(excerpt):
    amounts=[(Decimal(m['number'].replace(',','')),m['currency'].upper(),m['scale'].lower()) for m in AMOUNT.finditer(excerpt)]
    for match in AMOUNT_RANGE.finditer(excerpt):
        amounts.extend([
            (Decimal(match['lower'].replace(',','')),match['currency'].upper(),(match['lower_scale'] or match['upper_scale']).lower()),
            (Decimal(match['upper'].replace(',','')),(match['upper_currency'] or match['currency']).upper(),match['upper_scale'].lower()),
        ])
    return amounts


def source_unit_supported(unit,excerpt,values):
    if not re.fullmatch(r'(?:'+CURRENCIES+r')\s+(?:thousand|million|billion)s?',unit or '',re.I):
        return False
    currency=re.search(r'\b('+CURRENCIES+r')\b',unit or '',re.I)
    scale=re.search(r'\b(thousand|million|billion)s?\b',unit or '',re.I)
    if not currency or not scale:
        return False
    amounts=quoted_amounts(excerpt)
    return bool(values) and all(any(Decimal(str(value))==literal and code==currency[0].upper() and magnitude==scale[1].lower()
                                    for literal,code,magnitude in amounts) for value in values)


def restore_stated_amount_units(rule,excerpt):
    """500000000 USD + exact 'USD 500 million' -> 500 USD million.

    All numerical fields must resolve uniquely to one shared quoted unit. Mixed
    scales, conflicting currencies and invented amounts remain validation errors.
    """
    amounts=quoted_amounts(excerpt)
    fields=list(numeric_fields(rule))
    if not amounts or not fields:
        return False
    unit=rule.threshold_unit or ''
    currency=re.search(r'\b('+CURRENCIES+r')\b',unit,re.I)
    magnitude=re.search(r'\b(thousand|million|billion)s?\b',unit,re.I)
    chosen=[]
    for name,index,value in fields:
        target=Decimal(str(value))
        candidates=set()
        for literal,code,scale in amounts:
            if currency and code!=currency[0].upper():
                continue
            if magnitude and scale!=magnitude[1].lower():
                continue
            if target==literal or not magnitude and target==literal*SCALES[scale]:
                candidates.add((literal,code,scale))
        if len(candidates)!=1:
            return False
        chosen.append((name,index,*candidates.pop()))
    units={(code,scale) for _,_,_,code,scale in chosen}
    if len(units)!=1:
        return False
    code,scale=units.pop()
    # An unrelated dimensional unit cannot be replaced merely because an amount
    # also appears in the supporting passage.
    remainder=re.sub(r'\b('+CURRENCIES+r'|thousand|million|billion)s?\b','',unit,flags=re.I).strip()
    if remainder:
        return False
    changed=unit!=code+' '+scale
    for name,index,literal,_,_ in chosen:
        value=float(literal)
        current=getattr(rule,name)
        if isinstance(current,list):
            replacement=list(current);changed|=replacement[index]!=value
            replacement[index]=value;setattr(rule,name,replacement)
        else:
            changed|=current!=value;setattr(rule,name,value)
    rule.threshold_unit=code+' '+scale
    return changed
