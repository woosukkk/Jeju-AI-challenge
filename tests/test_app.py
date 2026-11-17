from pathlib import Path

from streamlit.testing.v1 import AppTest

from trade_itsuda import store


def app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'app.sqlite3'))
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('LLM_MODEL', '')
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('NTS_API_KEY', '')
    monkeypatch.setenv('ALLOW_EXTERNAL_DATA', 'false')
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=15).run()


def test_import_report_lists_skipped_rows(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    at.session_state['import_report'] = [{'제외 사유': '빈 값 또는 형식 오류: 생산품', '행 수': 2, '원본 행 번호 (앞 20개)': '3, 7'}]
    at.radio(key='page').set_value('데이터 관리').run()
    assert not at.exception
    assert any('제외한 행' in caption.value for caption in at.caption)
    assert at.dataframe[0].value.iloc[0]['행 수'] == 2


def test_demo_search_compare_and_download_without_keys(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    assert not at.exception
    at.radio(key='page').set_value('데이터 관리').run()
    at.button(key='load_demo').click().run()
    assert not at.exception
    at.radio(key='page').set_value('거래처 찾기').run()
    at.text_input(key='query').set_value('라벨 스티커')
    at.button(key='search_submit').click().run()
    assert not at.exception
    at.button(key='search_add_demo-print').click().run()
    at.radio(key='page').set_value('견적 비교').run()
    assert not at.exception
    values = {'업체명 (직접 입력할 때)': '기존 거래업체', '품목': '라벨',
              '규격 (예: 가로 50mm × 세로 50mm / 무광)': '50mm', '수량': '1000', '단위 (예: 개)': '개',
              '단가 (미확인이면 빈칸)': '100', '배송비 (세금 포함, 무료이면 0)': '0', '추가 비용 (세금 포함, 없으면 0)': '0'}
    for widget in at.text_input:
        if widget.label in values:
            widget.set_value(values[widget.label])
    next(w for w in at.selectbox if w.label == '단가의 세금 포함 여부').set_value('포함')
    next(w for w in at.checkbox if w.label == '원문과 대조해 입력값을 확인했습니다').check()
    at.button(key='save_quote').click().run()
    assert not at.exception
    saved = store.quotes(tmp_path / 'app.sqlite3')
    assert len(saved) == 1 and saved[0].company_name == '기존 거래업체'
    assert at.dataframe[0].value.iloc[0]['총액'] == '100000.00'
    assert len(at.get('download_button')) == 2
    baseline = saved[0].id
    next(w for w in at.selectbox if w.label == '견적 업체').set_value('demo-print').run()
    next(w for w in at.text_input if w.label == '단가 (미확인이면 빈칸)').set_value('90')
    at.button(key='save_quote').click().run()
    saved = store.quotes(tmp_path / 'app.sqlite3')
    assert len(saved) == 2
    at.multiselect(key='compare_ids').set_value([q.id for q in saved]).run()
    at.selectbox(key='baseline_id').set_value(baseline).run()
    assert not at.exception
    table = at.dataframe[0].value
    assert table.loc[table['업체'] == '가상 한라라벨', '기준 대비 차액'].iloc[0] == '-10000.00'
    at.radio(key='page').set_value('최근 관심 업체').run()
    assert not at.exception
    assert any('관심 1회' in element.value for element in at.caption)


def test_inquiry_and_empty_popularity(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    at.radio(key='page').set_value('최근 관심 업체').run()
    assert any('아직 집계된' in element.value for element in at.info)
    at.radio(key='page').set_value('문의 준비').run()
    for key, value in {'inquiry_company': '기존 업체', 'inquiry_item': '박스', 'inquiry_spec': '20cm',
                       'inquiry_quantity': '100', 'inquiry_unit': '개'}.items():
        at.text_input(key=key).set_value(value)
    at.button(key='create_inquiry').click().run()
    assert not at.exception
    assert any('아직 발송되지' in element.value for element in at.text)
