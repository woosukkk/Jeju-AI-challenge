from decimal import Decimal

import pytest
from pydantic import ValidationError

from trade_itsuda.models import Company, Quote
from trade_itsuda.store import companies, initialize, quotes, save_quotes


def test_quote_decimal_round_trip_and_unknown_cost(tmp_path):
    path = tmp_path / 'test.db'
    initialize(path)
    initialize(path)
    quote = Quote(id='q', company_id='existing', company_name='기준업체', item='병',
                  specification='100ml', unit='개', quantity='100', unit_price='10.15')
    save_quotes(path, [quote])
    restored = quotes(path)[0]
    assert restored.unit_price == Decimal('10.15')
    assert restored.shipping is None
    assert companies(path) == []


@pytest.mark.parametrize('changes', [{'business_number': '12x'}, {'website': 'javascript:alert(1)'}, {'unknown_field': 'x'}])
def test_company_boundary_validation(changes):
    data = dict(id='1', name='가상 업체', industry='인쇄', products='라벨', region='제주',
                source_name='합성', source_date='2026-11-17')
    with pytest.raises(ValidationError):
        Company(**(data | changes))


@pytest.mark.parametrize('quantity', ['0', '-1', 'NaN', 'Infinity'])
def test_invalid_quote_quantities(quantity):
    with pytest.raises(ValidationError):
        Quote(id='q', company_id='e', company_name='기준', item='병', specification='100ml', unit='개', quantity=quantity)
