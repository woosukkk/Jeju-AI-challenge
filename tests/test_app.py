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


def with_demo(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    at.radio(key='page').set_value('데이터 관리').run()
    at.button(key='load_demo').click().run()
    at.radio(key='page').set_value('거래처 찾기').run()
    assert not at.exception
    return at


def fill(at, values: dict[str, str]):
    for widget in at.text_input:
        if widget.label in values:
            widget.set_value(values[widget.label])


def save_quote(at, price: str):
    fill(at, {'단가': price, '배송비 (세금 포함)': '0', '추가 비용 (세금 포함)': '0'})
    next(w for w in at.selectbox if w.label == '단가에 부가세 포함?').set_value('포함')
    next(w for w in at.checkbox if w.label == '견적서 원문과 대조해 입력값을 확인했습니다').check()
    at.button(key='save_quote').click().run()
    assert not at.exception


def test_import_report_lists_skipped_rows(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    at.session_state['import_report'] = [{'제외 사유': '빈 값 또는 형식 오류: 생산품', '행 수': 2, '원본 행 번호 (앞 20개)': '3, 7'}]
    at.radio(key='page').set_value('데이터 관리').run()
    assert not at.exception
    assert any('제외한 행' in caption.value for caption in at.caption)
    assert at.dataframe[0].value.iloc[0]['행 수'] == 2


def test_wizard_from_need_to_comparison_without_keys(monkeypatch, tmp_path):
    at = with_demo(monkeypatch, tmp_path)
    # 1단계: 이용 목적·품목·기존 거래처만 묻는다.
    assert at.session_state['step'] == 1 and not at.text_area
    at.radio(key='w_journey').set_value('기존 거래처와 비교').run()
    at.text_input(key='w_query').set_value('라벨 스티커')
    at.text_input(key='w_existing').set_value('기존 거래업체')
    at.button(key='n1_next').click().run()
    # 2단계: 지역을 시 → 읍면동 순서로 고르고 후보를 찾는다.
    assert at.session_state['step'] == 2 and at.radio(key='w_city').options == ['전체', '서귀포시', '제주시']
    at.button(key='n2_next').click().run()
    assert at.session_state['step'] == 3 and not at.exception
    at.button(key='search_add_demo-print').click().run()
    assert at.session_state['shortlist'] == ['demo-print']
    at.button(key='n3_next').click().run()
    # 4단계: 조건을 한 번 적으면 기존 업체와 후보 모두의 문의 초안을 만든다.
    assert at.session_state['step'] == 4
    at.button(key='create_inquiry').click().run()
    assert not at.session_state['drafts'] and at.error  # 품목을 비우면 초안을 만들지 않는다.
    at.text_input(key='w_item').set_value('라벨 스티커')
    at.text_input(key='w_spec').set_value('50mm')
    at.text_input(key='w_quantity').set_value('1000')
    at.button(key='create_inquiry').click().run()
    assert set(at.session_state['drafts']) == {'existing', 'demo-print'}
    assert all('아직 발송되지' in text for text in at.session_state['drafts'].values())
    at.button(key='n4_next').click().run()
    # 5단계: 4단계 조건이 견적 칸에 채워지고, 금액만 넣어 저장한다.
    assert at.session_state['step'] == 5
    assert next(w for w in at.text_input if w.label == '수량').value == '1000'
    save_quote(at, '100')
    at.radio(key='w_quote_target').set_value('가상 한라라벨').run()
    save_quote(at, '90')
    saved = {q.company_name: q for q in store.quotes(tmp_path / 'app.sqlite3')}
    assert set(saved) == {'기존 거래업체', '가상 한라라벨'}
    assert saved['기존 거래업체'].item == '라벨 스티커' and saved['기존 거래업체'].specification == '50mm'
    at.button(key='n5_next').click().run()
    # 6단계: 기존 거래처가 기준 견적이 되고 차액을 계산한다.
    assert at.session_state['step'] == 6 and not at.exception
    table = at.dataframe[0].value  # 접힌 '자세한 비교표': 금액은 화면용 형식
    assert table.loc[table['업체'] == '가상 한라라벨', '기준 대비 차액'].iloc[0] == '-10,000원'
    assert table.loc[table['업체'] == '가상 한라라벨', '총액'].iloc[0] == '90,000원'
    # 결론 한 줄과 카드: 가장 싼 곳과 차액(10%)을 보여 준다.
    verdict = next(str(h.proto) for h in at.get('html') if 'tis-verdict' in str(h.proto))
    assert '가상 한라라벨' in verdict and '10,000원' in verdict and '(10.0%) 저렴' in verdict
    assert len(at.get('download_button')) == 2
    at.button(key='n6_back').click().run()
    assert at.session_state['step'] == 5
    at.radio(key='page').set_value('최근 관심 업체').run()
    # 업체 줄 머리(상자 없는 목록 줄)에 관심 횟수가 붙는다.
    assert any('관심 1회' in str(h.proto) for h in at.get('html'))


def step_indicator(at) -> str:
    return next(str(h.proto) for h in at.get('html') if 'tis-steps' in str(h.proto) and 'aria-label' in str(h.proto))


def test_wizard_blocks_missing_inputs_and_restarts(monkeypatch, tmp_path):
    at = with_demo(monkeypatch, tmp_path)
    # KRDS 단계 표시기: 현재 단계 문구와 aria-current가 있어야 한다.
    assert '6단계 중 1단계' in step_indicator(at) and 'aria-current' in step_indicator(at)
    at.button(key='n1_next').click().run()
    assert at.session_state['step'] == 1 and any('품목' in e.value for e in at.error)
    at.text_input(key='w_query').set_value('반도체')
    at.button(key='n1_next').click().run()
    at.button(key='n2_next').click().run()
    assert any('근거를 찾지 못했습니다' in e.value for e in at.info)
    at.button(key='n3_next').click().run()
    assert at.session_state['step'] == 3 and any('1곳 이상' in e.value for e in at.error)
    assert '6단계 중 3단계' in step_indicator(at) and step_indicator(at).count('class=\\"done\\"') == 2
    at.button(key='n3_back').click().run()
    assert at.session_state['step'] == 2


def test_empty_popularity(monkeypatch, tmp_path):
    at = app(monkeypatch, tmp_path)
    at.radio(key='page').set_value('최근 관심 업체').run()
    assert any('아직 집계된' in element.value for element in at.info)
