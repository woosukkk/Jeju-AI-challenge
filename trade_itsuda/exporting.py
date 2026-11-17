import csv
import html
from io import StringIO

from .comparison import Comparison, today
from .models import Company


def inquiry(company_name: str, item: str, specification: str, quantity: str, unit: str, notes: str = '') -> str:
    if not all(value.strip() for value in [company_name, item, specification, quantity, unit]):
        raise ValueError('업체명·품목·규격·수량·단위를 입력하세요.')
    if any(len(value) > 2000 for value in [company_name, item, specification, quantity, unit, notes]):
        raise ValueError('입력 항목은 각각 2,000자 이하여야 합니다.')
    return (f'{company_name} 담당자님께\n\n아래 조건의 취급·공급 가능 여부와 견적을 문의드립니다.\n'
            f'- 품목: {item}\n- 규격: {specification}\n- 요청 수량: {quantity} {unit}\n'
            f'- 추가 요청: {notes or "없음"}\n\n'
            '단가와 통화, 부가세 포함 여부·세율, 세금 포함 배송비·추가 비용, 최소 주문 수량, '
            '납기, 견적 유효기간을 알려주시면 감사하겠습니다.\n'
            '거래 조건과 업체 담당자 연락처도 함께 확인 부탁드립니다.\n\n'
            '이 문서는 거래잇수다에서 만든 문의 초안이며 아직 발송되지 않았습니다.\n')


def rows_for_export(rows: list[Comparison]):
    return [{'업체': r.quote.company_name, '품목': r.quote.item, '규격': r.quote.specification,
             '수량': str(r.quote.quantity), '단위': r.quote.unit, '통화': r.quote.currency,
             '총액': str(r.total) if r.total is not None else '미확정',
             '기준 대비 차액': str(r.difference) if r.difference is not None else '비교 불가',
             '비교 제한': '; '.join(r.issues), '추가 확인': '; '.join(r.warnings),
             '견적 근거': r.quote.source_name, '발행일': str(r.quote.issued_at or '미확인'),
             '유효기간': str(r.quote.valid_until or '미확인')} for r in rows]


def csv_report(rows: list[Comparison]) -> bytes:
    output = StringIO(newline='')
    data = rows_for_export(rows)
    if not data:
        raise ValueError('비교 결과가 없습니다.')
    writer = csv.DictWriter(output, fieldnames=list(data[0]))
    writer.writeheader()
    for row in data:
        safe = {key: ("'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value)
                for key, value in row.items()}
        writer.writerow(safe)
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def html_report(rows: list[Comparison], baseline_id: str, companies: list[Company]) -> str:
    if not rows or baseline_id not in {r.quote.id for r in rows}:
        raise ValueError('기준 견적을 포함한 비교 결과가 필요합니다.')
    escape = lambda value: html.escape(str(value), quote=True)
    data = rows_for_export(rows)
    baseline = next(r.quote.company_name for r in rows if r.quote.id == baseline_id)
    table = '<tr>' + ''.join('<th>' + escape(key) + '</th>' for key in data[0]) + '</tr>'
    for row in data:
        table += '<tr>' + ''.join('<td>' + escape(v) + '</td>' for v in row.values()) + '</tr>'
    sources = []
    used_ids = {r.quote.company_id for r in rows}
    for c in companies:
        if c.id in used_ids:
            sources.append(f'<li>{escape(c.name)}: {escape(c.source_name)} / 데이터 기준일 {escape(c.source_date)}'
                           + (' / 가상 데이터' if c.is_demo else '') + '</li>')
    inputs = ''.join('<details><summary>' + escape(r.quote.company_name) + ' 계산 입력값</summary><pre>'
                     + escape(r.quote.model_dump_json(indent=2)) + '</pre></details>' for r in rows)
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><title>거래잇수다 비교 보고서</title>'
            '<style>body{font-family:sans-serif;margin:32px;line-height:1.6}table{border-collapse:collapse}'
            'td,th{border:1px solid #aaa;padding:8px}pre{white-space:pre-wrap}</style>'
            f'<h1>거래잇수다 견적 비교</h1><p>작성일 {today()} / 기준 업체 {escape(baseline)}</p>'
            '<p>총액 = 수량 × 단가 × (세금 별도이면 1 + 명시 세율) + 세금 포함 배송비 + 세금 포함 추가 비용. '
            '소수 둘째 자리에서 반올림한 표시 금액이며, 실제 청구 시 반올림 방식은 업체에 확인해야 합니다. '
            '차액은 후보 총액 − 기준 총액입니다. 품목·규격·단위·수량·통화가 같을 때만 차액을 계산합니다.</p>'
            '<table>' + table + '</table><h2>계산 입력값</h2>' + inputs + '<h2>기업 데이터 출처</h2><ul>' + ''.join(sources) + '</ul>'
            '<p>견적은 사용자 확인 자료입니다. 과거 기업 기록·관심 순위·국세청 사업자 상태는 현재 공급 능력이나 신뢰도를 보증하지 않습니다. '
            '실제 품목·납기·연락처·거래 조건은 업체에 확인하세요. 이 보고서는 계약이나 거래 보증이 아닙니다.</p></html>')
