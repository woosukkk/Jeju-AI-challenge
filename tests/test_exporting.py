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
