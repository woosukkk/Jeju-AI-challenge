"""문의 초안 끝에 붙이는 회신 양식과, 업체가 채워 보낸 회신을 AI 없이 읽는 코드.

흐름: 4단계 초안(회신 양식 포함) 다운로드 → 업체에 보냄 → 업체가 양식을 채워 회신 → 5단계에 붙여 넣으면 견적 칸이 채워진다.
양식을 벗어난 자유 형식 견적서는 기존처럼 AI 추출(agent.extract_quote)을 쓴다.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from .models import QuoteExtraction

START = '[회신 양식]'
END = '[회신 양식 끝]'
# 양식의 칸 이름 → 견적 필드. 칸 이름 안에는 콜론(:)을 쓰지 않는다(값과 구분하기 위해).
FIELDS = [('문의 업체', 'company_name'), ('단가(원)', 'unit_price'), ('부가세', 'tax'), ('별도일 때 세율(%)', 'tax_rate'),
          ('배송비(원, 세금 포함)', 'shipping'), ('추가 비용(원, 설치·디자인 등, 세금 포함)', 'extra_cost'),
          ('최소 주문 수량', 'minimum_order'), ('납기(일)', 'lead_days'), ('견적 유효기간(YYYY-MM-DD)', 'valid_until')]
TAX_CHOICES = '포함 / 별도 (하나만 남겨 주세요)'
NONE_WORDS = {'없음', '무료', '없습니다', '해당 없음'}


def reply_form(company_name: str, item: str, specification: str, quantity: str, unit: str) -> str:
    """업체가 채워 보낼 회신 양식. 모르는 칸은 비워 두면 된다."""
    lines = [f'{START} 아래 칸을 채워 이 글 그대로 회신해 주세요. 모르는 칸은 비워 두셔도 됩니다.',
             f'(문의 내용: {item} / {specification} / {quantity} {unit})']
    for label, field in FIELDS:
        value = company_name if field == 'company_name' else TAX_CHOICES if field == 'tax' else ''
        lines.append(f'{label}: {value}'.rstrip() + (' ' if not value else ''))
    lines.append(END)
    return '\n'.join(lines) + '\n'


def amount(value: str) -> Decimal | None:
    text = value.replace(',', '').replace('원', '').replace(' ', '').strip()
    if text in NONE_WORDS:
        return Decimal(0)
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def parse_reply(text: str) -> QuoteExtraction | None:
    """채워진 회신 양식을 읽는다. 양식이 없으면 None. 읽지 못한 칸은 비워 둔다(추정하지 않음)."""
    start = text.find(START)
    if start < 0:
        return None
    end = text.find(END, start)
    block = text[start:end if end > 0 else None]
    raw: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip().lstrip('>').strip()  # 메일 회신의 인용 표시('> ')를 뗀다
        for label, field in FIELDS:
            if line.startswith(label):
                raw[field] = line[len(label):].lstrip(' :：').strip()
                break
    values: dict = {}
    if raw.get('company_name'):
        values['company_name'] = raw['company_name'][:200]
    for field in ('unit_price', 'shipping', 'extra_cost', 'minimum_order'):
        number = amount(raw.get(field, '')) if raw.get(field) else None
        if number is not None and not (field == 'minimum_order' and number == 0):
            values[field] = number
    tax = raw.get('tax', '')
    if '포함' in tax and '별도' not in tax:
        values['tax_included'] = True
    elif '별도' in tax and '포함' not in tax:
        values['tax_included'] = False
    rate = amount(raw.get('tax_rate', '').replace('%', '')) if raw.get('tax_rate') else None
    if rate is not None and rate <= 100:
        values['tax_rate'] = rate / 100
    days = re.fullmatch(r'\s*(\d{1,4})\s*(일)?\s*', raw.get('lead_days', ''))
    if days:
        values['lead_days'] = int(days[1])
    found = re.fullmatch(r'\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})\.?\s*', raw.get('valid_until', ''))
    if found:
        try:
            values['valid_until'] = date(int(found[1]), int(found[2]), int(found[3]))
        except ValueError:
            pass
    try:
        return QuoteExtraction(**values)
    except ValidationError:
        return QuoteExtraction()
