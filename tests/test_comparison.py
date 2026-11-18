from datetime import date
from decimal import Decimal
from typing import Any

from trade_itsuda.comparison import calculate, compare
from trade_itsuda.models import Quote


def quote(**changes):
    values: dict[str, Any] = dict(id='a', company_id='a', company_name='기존 업체', item='라벨', specification='50mm', unit='개',
                  quantity='3', unit_price='0.1', tax_included=False, tax_rate='0.1', shipping='0', extra_cost='0', confirmed=True)
    return Quote(**(values | changes))


def test_decimal_tax_and_unknown_is_not_zero():
    assert calculate(quote()).total == Decimal('0.33')
    assert calculate(quote(shipping=None)).total is None
    assert calculate(quote(tax_rate=None)).total is None
    assert calculate(quote(confirmed=False)).total is None
    assert calculate(quote(unit_price='0')).total == 0


def test_expiry_moq_and_future_issue():
    assert calculate(quote(valid_until=date(2020, 1, 1))).total is None
    assert calculate(quote(minimum_order=4)).total is None
    assert calculate(quote(issued_at=date(2099, 1, 1))).total is None


def test_comparison_same_conditions_only():
    rows = compare([quote(), quote(id='b', unit_price='0.2'), quote(id='c', quantity=4)], 'a')
    assert rows[1].difference == Decimal('0.33')
    assert rows[2].difference is None
    assert '수량' in rows[2].issues[0]
    assert compare([quote(shipping=None), quote(id='b')], 'a')[1].difference is None


def test_quote_currency_words_become_codes():
    assert quote(currency='원').currency == 'KRW' and quote(currency='usd').currency == 'USD'
