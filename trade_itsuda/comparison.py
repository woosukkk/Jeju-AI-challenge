from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from .models import Quote


def today() -> date:
    return datetime.now(ZoneInfo('Asia/Seoul')).date()


@dataclass
class Comparison:
    quote: Quote
    total: Decimal | None = None
    difference: Decimal | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def calculate(quote: Quote, as_of: date | None = None) -> Comparison:
    as_of = as_of or today()
    row = Comparison(quote)
    if not quote.confirmed:
        row.issues.append('견적 원문 확인·확정 필요')
    for field_name, label in [('unit_price', '단가'), ('shipping', '배송비'), ('extra_cost', '추가 비용'), ('tax_included', '세금 포함 여부')]:
        if getattr(quote, field_name) is None:
            row.issues.append(f'{label} 미확인')
    if quote.tax_included is False and quote.tax_rate is None:
        row.issues.append('세율 미확인')
    if quote.minimum_order is not None and quote.quantity < quote.minimum_order:
        row.issues.append('최소 주문 수량 미달')
    if quote.valid_until and quote.valid_until < as_of:
        row.issues.append('유효기간 만료')
    if quote.issued_at and quote.issued_at > as_of:
        row.issues.append('견적 발행일이 미래임')
    for field_name, label in [('minimum_order', '최소 주문 수량'), ('lead_days', '납기'), ('valid_until', '유효기간')]:
        if getattr(quote, field_name) is None:
            row.warnings.append(f'{label} 미확인')
    if not row.issues:
        assert quote.unit_price is not None and quote.shipping is not None and quote.extra_cost is not None
        goods = quote.quantity * quote.unit_price
        if quote.tax_included is False:
            assert quote.tax_rate is not None
            goods *= 1 + quote.tax_rate
        # 배송비·추가 비용은 사용자가 확인한 세금 포함 최종 금액으로 입력.
        row.total = (goods + quote.shipping + quote.extra_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return row


def compare(quotes: list[Quote], baseline_id: str, as_of: date | None = None) -> list[Comparison]:
    if len({q.id for q in quotes}) != len(quotes):
        raise ValueError('중복된 견적입니다.')
    baseline = next((q for q in quotes if q.id == baseline_id), None)
    if baseline is None:
        raise ValueError('비교 기준 견적을 선택하세요.')
    rows = [calculate(q, as_of) for q in quotes]
    base_row = next(row for row in rows if row.quote.id == baseline_id)
    for row in rows:
        mismatch = []
        for field_name, label in [('item', '품목'), ('specification', '규격'), ('unit', '단위'), ('quantity', '수량'), ('currency', '통화')]:
            current, base = getattr(row.quote, field_name), getattr(baseline, field_name)
            if isinstance(current, str):
                current, base = ' '.join(current.casefold().split()), ' '.join(base.casefold().split())
            if current != base:
                mismatch.append(label)
        if mismatch:
            row.issues.append('기준 견적과 다른 조건: ' + ', '.join(mismatch))
        elif row.total is not None and base_row.total is not None:
            row.difference = row.total - base_row.total
    return rows
