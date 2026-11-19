import csv
import html
from io import StringIO
from typing import Callable

from .comparison import Comparison, today
from .models import Company
from .reply import reply_form


def inquiry(company_name: str, item: str, specification: str, quantity: str, unit: str, notes: str = '',
            questions: list[str] | None = None) -> str:
    if not all(value.strip() for value in [company_name, item, specification, quantity, unit]):
        raise ValueError('업체명·품목·규격·수량·단위를 입력하세요.')
    if any(len(value) > 2000 for value in [company_name, item, specification, quantity, unit, notes]):
        raise ValueError('입력 항목은 각각 2,000자 이하여야 합니다.')
    extra = ''
    if questions:
        extra = '함께 확인 부탁드립니다.\n' + ''.join(f'{n}. {q}\n' for n, q in enumerate(questions, start=1)) + '\n'
    return (f'{company_name} 담당자님께\n\n아래 조건의 취급·공급 가능 여부와 견적을 문의드립니다.\n'
            f'- 품목: {item}\n- 규격: {specification}\n- 요청 수량: {quantity} {unit}\n'
            f'- 추가 요청: {notes or "없음"}\n\n'
            + extra +
            '견적은 아래 회신 양식을 채워 보내 주시면 감사하겠습니다. 거래 조건과 담당자 연락처도 함께 알려 주세요.\n\n'
            + reply_form(company_name, item, specification, quantity, unit) + '\n'
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


def search_section(search: dict | None, imports: list[dict] | None, escape: Callable[[object], str]) -> str:
    """보고서의 '후보를 찾은 과정': 요청·조건·방식(모델)·Agent 단계·데이터 파일 해시. 같은 파일과 기록으로 다시 확인할 수 있게 한다."""
    parts = []
    if search:
        rows = [('요청', search.get('request')), ('지역', search.get('region')), ('업종 조건', search.get('industry')),
                ('찾은 방식', search.get('method')), ('찾은 시각', search.get('searched_at'))]
        parts.append('<table>' + ''.join(f'<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>' for k, v in rows if v) + '</table>')
        if search.get('steps'):
            parts.append('<p>AI Agent가 수행한 단계</p><ol>' + ''.join(f'<li>{escape(step)}</li>' for step in search['steps']) + '</ol>')
        if search.get('summary'):
            parts.append(f'<p>Agent 요약(숫자는 도구 결과에 있는 값만 허용): {escape(search["summary"])}</p>')
        if search.get('found'):
            parts.append('<p>찾은 후보: ' + escape(', '.join(search['found'])) + '</p>')
    if imports:
        parts.append('<p>검색한 데이터 파일</p><ul>' + ''.join(
            f'<li>{escape(i.get("source_name"))} / {escape(i.get("row_count"))}곳 / 가져온 시각 {escape(i.get("imported_at"))}'
            f' / SHA-256 <code>{escape(i.get("sha256"))}</code></li>' for i in imports) + '</ul>')
    if not parts:
        return ''
    return ('<h2>후보를 찾은 과정</h2>' + ''.join(parts)
            + '<p>AI의 후보 선택과 문장은 모델·시점에 따라 달라질 수 있습니다. 숫자 계산은 AI가 아니라 코드가 합니다.</p>')


def html_report(rows: list[Comparison], baseline_id: str, companies: list[Company], search: dict | None = None,
                imports: list[dict] | None = None) -> str:
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
            '소수 셋째 자리에서 반올림해 소수 둘째 자리까지 표시하며, 실제 청구 시 반올림 방식은 업체에 확인해야 합니다. '
            '차액은 후보 총액 − 기준 총액입니다. 품목·규격·단위·수량·통화가 같을 때만 차액을 계산합니다.</p>'
            '<table>' + table + '</table>' + search_section(search, imports, escape) + '<h2>계산 입력값</h2>' + inputs + '<h2>기업 데이터 출처</h2><ul>' + ''.join(sources) + '</ul>'
            '<p>견적은 사용자 확인 자료입니다. 과거 기업 기록·관심 순위·국세청 사업자 상태는 현재 공급 능력이나 신뢰도를 보증하지 않습니다. '
            '실제 품목·납기·연락처·거래 조건은 업체에 확인하세요. 이 보고서는 계약이나 거래 보증이 아닙니다.</p></html>')
