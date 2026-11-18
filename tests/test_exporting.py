from trade_itsuda.comparison import compare
from trade_itsuda.exporting import csv_report, html_report, inquiry
from trade_itsuda.models import Quote


def test_export_escapes_html_and_spreadsheet_formula():
    q = Quote(id='a', company_id='a', company_name='=HYPERLINK("evil")', item='<script>alert(1)</script>',
              specification='50mm', unit='개', quantity=1)
    rows = compare([q], 'a')
    page = html_report(rows, 'a', [])
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert "'=HYPERLINK" in csv_report(rows).decode('utf-8-sig')
    assert '미확정' in page
    assert '아직 발송되지' in inquiry('업체', '라벨', '50mm', '1000', '개')


def test_report_records_how_candidates_were_found():
    from trade_itsuda.comparison import compare
    from trade_itsuda.models import Quote
    q = Quote(id='a', company_id='a', company_name='기존', item='간판', specification='1200', unit='개', quantity='1',
              unit_price='1', tax_included=True, shipping='0', extra_cost='0', confirmed=True)
    search = {'request': '가게 간판 <b>', 'region': '제주시', 'method': 'AI Agent (openai / gpt-5.4-mini)',
              'steps': ["업종 분류 확인: '간판' → 관련 업소 195곳"], 'summary': '후보 5곳', 'found': ['조아간판']}
    imports = [{'source_name': '상가 정보', 'row_count': 57347, 'imported_at': '2026-11-17', 'sha256': 'abc123'}]
    page = html_report(compare([q], 'a'), 'a', [], search, imports)
    assert '후보를 찾은 과정' in page and 'gpt-5.4-mini' in page and '관련 업소 195곳' in page
    assert 'abc123' in page and '57347곳' in page and '&lt;b&gt;' in page  # 입력은 이스케이프한다.
    assert '후보를 찾은 과정' not in html_report(compare([q], 'a'), 'a', [])  # 기록이 없으면 절을 넣지 않는다.
