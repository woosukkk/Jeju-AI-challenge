from datetime import date
from decimal import Decimal

from trade_itsuda.exporting import inquiry
from trade_itsuda.models import QuoteExtraction
from trade_itsuda.reply import parse_reply


def draft() -> str:
    return inquiry('가상 조아간판', 'LED 간판', '1200x600 LED', '1', '개')


def parsed(text: str) -> QuoteExtraction:
    result = parse_reply(text)
    assert result is not None
    return result


def fill(text: str, answers: dict[str, str]) -> str:
    for label, value in answers.items():
        text = text.replace(f'{label}: ', f'{label}: {value}', 1)
    return text


def test_draft_carries_a_reply_form_that_reads_back_without_ai():
    text = draft()
    assert '[회신 양식]' in text and '[회신 양식 끝]' in text and '아직 발송되지' in text
    assert parsed(text).model_dump(exclude_none=True) == {'company_name': '가상 조아간판'}  # 빈 양식은 업체명만
    reply = fill(text, {'사업자등록번호': '124-81-00998', '단가(원)': '650,000원', '별도일 때 세율(%)': '10%', '배송비(원, 세금 포함)': '없음',
                        '추가 비용(원, 설치·디자인 등, 세금 포함)': '50,000', '최소 주문 수량': '1',
                        '납기(일)': '10일', '견적 유효기간(YYYY-MM-DD)': '2026.12.17'})
    reply = reply.replace('포함 / 별도 (하나만 남겨 주세요)', '별도')
    quoted = '\n'.join('> ' + line for line in reply.splitlines())
    got = parsed('업체 회신 메일 머리말\n' + quoted)  # 메일 회신처럼 모든 줄에 인용 표시가 붙어도 읽는다
    assert (got.unit_price, got.tax_included, got.tax_rate) == (Decimal('650000'), False, Decimal('0.1'))
    assert (got.shipping, got.extra_cost, got.lead_days, got.valid_until) == (0, Decimal('50000'), 10, date(2026, 12, 17))
    assert got.business_number == '1248100998'
    assert parsed(fill(text, {'사업자등록번호': '123-45'})).business_number is None  # 10자리가 아니면 비운다


def test_unclear_or_missing_values_stay_blank():
    assert parse_reply('양식 없는 자유 형식 견적서') is None
    reply = fill(draft(), {'단가(원)': '문의 바람', '납기(일)': '2주', '견적 유효기간(YYYY-MM-DD)': '12월 말'})
    got = parsed(reply)
    # 부가세 칸을 지우지 않았으면(포함/별도 둘 다) 정하지 않는다. 숫자가 아닌 값은 추정하지 않는다.
    assert got.tax_included is None and got.unit_price is None and got.lead_days is None and got.valid_until is None
