from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import streamlit as st
from pydantic import ValidationError

from trade_itsuda import store
from trade_itsuda.agent import (AgentError, explain_comparison, extract_quote, inquiry_questions, quote_text, run_agent,
                                trace_lines)
from trade_itsuda.business import refresh_status
from trade_itsuda.comparison import compare
from trade_itsuda.config import settings
from trade_itsuda.exporting import csv_report, html_report, inquiry, rows_for_export
from trade_itsuda.ingest import demo_companies, import_companies, parse_file
from trade_itsuda.models import Company, Quote, SearchRequest
from trade_itsuda.popularity import popular, prune_events, record_event
from trade_itsuda.retrieval import load_encoder, search

STEPS = ['필요 품목', '지역', '후보 고르기', '문의 준비', '견적 입력', '비교 결과']
JOURNEYS = ['새 거래처 찾기', '기존 거래처와 비교']
EXISTING = 'existing'
OTHER = 'other'

st.set_page_config(page_title='거래잇수다', page_icon=':material/handshake:', layout='centered',
                   initial_sidebar_state='collapsed')
# KRDS(범정부 디자인 시스템) 표준형 색상: primary-50 #256ef4, primary-5 #ecf2fe, gray-20 #cdd1d5, gray-50 #6d7882.
# 테마 색·글꼴은 .streamlit/config.toml, 여기서는 앱 틀(상단 앱 바·화면 카드·하단 버튼 바)과
# 기본 위젯에 없는 단계 표시기·목적 카드 모양을 정한다.
st.html('''<style>
/* 앱 틀: Streamlit 기본 머리줄·메뉴·사이드바를 숨기고, 회색 바탕 위 가운데 흰 화면 카드로 보이게 한다. */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], footer { display: none !important; }
.stApp { background: #f4f5f6; }
[data-testid="stMainBlockContainer"] { max-width: 960px; padding: 0 16px 48px; }
/* Streamlit은 컨테이너를 stLayoutWrapper로 한 번 더 감싸므로 고정(sticky)은 그 바깥 틀에 건다. */
[data-testid="stLayoutWrapper"]:has(> .st-key-appbar) { position: sticky; top: 0; z-index: 50; }
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-navbar_"]) { position: sticky; bottom: 0; z-index: 40; }
.st-key-appbar { background: #fff; padding: 10px 0; margin-bottom: 20px;
  box-shadow: 0 0 0 100vmax #fff, 0 1px 0 100vmax #e6e8ea; clip-path: inset(0 -100vmax -1px -100vmax); }
.tis-brand { display: flex; align-items: center; gap: 10px; }
.tis-logo { width: 36px; height: 36px; border-radius: 10px; background: #256ef4; color: #fff; font-weight: 800;
  display: flex; align-items: center; justify-content: center; font-size: 1.05rem; }
.tis-brand strong { display: block; font-size: 1.1rem; color: #1e2124; line-height: 1.2; }
.tis-brand small { display: block; font-size: 0.75rem; color: #6d7882; }
.tis-status { text-align: right; font-size: 0.78rem; color: #6d7882; }
.tis-status b { color: #1e2124; }
.tis-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 4px 1px 8px; }
.st-key-page [role="radiogroup"] { gap: 4px; justify-content: center; flex-wrap: nowrap; }
.st-key-page [role="radiogroup"] > div { margin: 0; }
.st-key-page [role="radiogroup"] label { margin: 0; padding: 8px 14px; border-radius: 999px; cursor: pointer; white-space: nowrap; }
.st-key-page [role="radiogroup"] label > div > div:not([data-testid="stMarkdownContainer"]) { display: none; }
@media (max-width: 900px) { .tis-status .count { display: none; } }
.st-key-page [role="radiogroup"] label:hover { background: #f4f5f6; }
.st-key-page [role="radiogroup"] label:has(input:checked) { background: #ecf2fe; }
.st-key-page [role="radiogroup"] label:has(input:checked) p { color: #256ef4; font-weight: 700; }
.st-key-page p { white-space: nowrap; }
.tis-brand strong, .tis-brand small, .tis-status { white-space: nowrap; }
[class*="st-key-navbar_"] [class*="_next"] { width: 100% !important; display: flex; justify-content: flex-end; }
[class*="st-key-navbar_"] [class*="_next"] [data-testid="stButton"], [class*="st-key-navbar_"] [class*="_next"] button { width: auto !important; }
.st-key-screen { background: #fff; border-radius: 20px; padding: 28px 32px 8px;
  box-shadow: 0 1px 2px rgba(30, 33, 36, 0.06), 0 8px 24px rgba(30, 33, 36, 0.05); }
[class*="st-key-navbar_"] { background: #fff; padding: 12px 0 16px;
  margin-top: 8px; border-top: 1px solid #e6e8ea; }
@media (max-width: 640px) {
  .st-key-screen { padding: 20px 16px 4px; border-radius: 16px; }
  .tis-brand small, .tis-status { display: none; }
  .st-key-screen h3 { font-size: 1.35rem; }
}
.tis-steps { list-style: none; display: flex; gap: 0; margin: 4px 0 8px; padding: 0; }
.tis-steps li { flex: 1; position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px;
  font-size: 0.82rem; color: #6d7882; text-align: center; }
.tis-steps li + li::before { content: ""; position: absolute; top: 15px; right: 50%; width: 100%; height: 2px;
  background: #cdd1d5; z-index: 0; }
.tis-steps li.done + li::before, .tis-steps li.current::before { background: #256ef4; }
.tis-steps .dot { position: relative; z-index: 1; width: 32px; height: 32px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-weight: 700; background: #fff; border: 2px solid #cdd1d5; color: #6d7882; }
.tis-steps li.done .dot { background: #256ef4; border-color: #256ef4; color: #fff; }
.tis-steps li.current .dot { border-color: #256ef4; color: #256ef4; background: #ecf2fe; }
.tis-steps li.current { color: #1e2124; font-weight: 700; }
.tis-steps .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.tis-step-count { font-size: 0.82rem; color: #6d7882; margin: 0; }
.st-key-w_journey div[role="radiogroup"] { gap: 16px; flex-wrap: wrap; }
.st-key-w_journey div[role="radiogroup"] > div { flex: 1 1 240px; padding: 16px 20px; border: 1px solid #cdd1d5;
  border-radius: 16px; background: #fff; margin: 0; cursor: pointer; }
.st-key-w_journey div[role="radiogroup"] > div:has(input:checked) { border-color: #256ef4; background: #ecf2fe;
  box-shadow: inset 0 0 0 1px #256ef4; }
.st-key-w_journey div[role="radiogroup"] > div label { font-weight: 700; }
@media (max-width: 640px) { .tis-steps .label { display: none; } }
/* 제주 포인트: 카드·상자는 제주도청 누리집처럼 둥글게(16px), 버튼·입력칸은 KRDS 6px 유지.
   AI가 만든 내용에만 제주 주황(#b34f00, 흰 배경 대비 약 7:1)을 쓴다. KRDS 강조색 규칙대로 화면의 5% 이하. */
[class*="st-key-card_"], .st-key-ai_summary, .st-key-ai_advice, [data-testid="stExpander"] details { border-radius: 16px !important; }
.st-key-ai_summary, .st-key-ai_advice { border-left: 4px solid #b34f00 !important; background: #fff8f2; }
.tis-ai-label { margin: 0; font-weight: 700; color: #1e2124; display: flex; align-items: center; gap: 8px; }
.tis-ai { display: inline-block; background: #b34f00; color: #fff; font-size: 0.75rem; font-weight: 700;
  line-height: 1; padding: 4px 8px; border-radius: 999px; letter-spacing: 0.02em; }
</style>''')
try:
    config = settings()
    store.initialize(config.database_path)
except (ValueError, OSError):
    st.error('환경 설정 또는 데이터 폴더를 확인하세요. README의 설치 절차를 참고하세요.')
    st.stop()
ai_ready = bool(config.llm_key and config.allow_external_data)

# 단계 사이에 유지할 값. 위젯 값은 화면을 떠나면 지워지므로 '다음'을 누를 때 여기에 옮겨 둔다.
FLOW_DEFAULTS = {
    'step': 1,
    'need': {'journey': JOURNEYS[0], 'query': '', 'existing': ''},
    'scope': {'city': '전체', 'region': '전체', 'industry': '전체', 'use_ai': True, 'semantic': False},
    'hits': [], 'questions': [], 'trace': [], 'summary': '', 'search_note': '', 'searched': False,
    'shortlist': [], 'conditions': {}, 'drafts': {}, 'inquiry_note': '',
    'flow_quotes': {}, 'extracted': {}, 'extraction_version': 0, 'advice': None,
}
for key, value in {'session_id': str(uuid4()), 'flash': '', **deepcopy(FLOW_DEFAULTS)}.items():
    st.session_state.setdefault(key, value)


@st.cache_data(max_entries=2)
def load_companies(path: str, version: int):
    return store.companies(path)


@st.cache_resource(max_entries=1)
def encoder_at(path: str):
    return load_encoder(path)


records = load_companies(str(config.database_path), config.database_path.stat().st_mtime_ns)
by_id = {c.id: c for c in records}
st.session_state.shortlist = [cid for cid in st.session_state.shortlist if cid in by_id]
# 상단 앱 바: 서비스 이름 · 메뉴 탭 · 상태. 사이드바 대신 앱처럼 위에 고정한다.
with st.container(key='appbar'):
    brand, menu, status = st.columns([3, 6, 2], vertical_alignment='center')
    with brand:
        st.html('<div class="tis-brand"><span class="tis-logo" aria-hidden="true">거</span>'
                '<div><strong>거래잇수다</strong><small>제주 거래처 찾기 · 견적 비교</small></div></div>')
    with menu:
        page = st.radio('메뉴', ['거래처 찾기', '최근 관심 업체', '데이터 관리'], key='page', horizontal=True,
                        label_visibility='collapsed')
    with status:
        dot = '#228738' if ai_ready else '#9e6a00'
        st.html(f'<div class="tis-status"><span class="count">업체 <b>{len(records):,}</b>곳</span>'
                f'<span class="tis-dot" style="background:{dot}"></span>AI {"켜짐" if ai_ready else "꺼짐"}</div>')
if st.session_state.flash:
    st.toast(st.session_state.flash, icon=':material/check_circle:')
    st.session_state.flash = ''
if any(c.is_demo for c in records):
    st.warning('가상 데이터로 기능을 체험 중입니다. 실제 기업 정보·대회 필수 데이터 활용 실적이 아닙니다.')


def go(step: int) -> None:
    st.session_state.step = step
    st.rerun()


def nav(back: int | None, next_label: str | None, key: str) -> bool:
    """화면 아래에 붙는 이전/다음 버튼 바. 이전은 바로 이동하고, 다음은 눌렸는지만 돌려준다(검증은 호출한 단계에서)."""
    with st.container(key=f'navbar_{key}'):
        left, right = st.columns([1, 1], vertical_alignment='center')
        with left:
            if back is not None and st.button('이전', key=f'{key}_back', icon=':material/arrow_back:'):
                go(back)
        with right:
            return bool(next_label) and st.button(next_label, key=f'{key}_next', type='primary', icon=':material/arrow_forward:')


def header(step: int) -> None:
    """KRDS 단계 표시기: 완료·현재·남은 단계를 구분하고, 화면 낭독기에는 '현재 단계'를 알린다."""
    items = []
    for i, name in enumerate(STEPS, start=1):
        state = 'done' if i < step else 'current' if i == step else 'todo'
        mark = '✓' if i < step else str(i)
        extra = ' aria-current="step"' if i == step else ''
        note = '<span class="sr">현재 단계</span>' if i == step else ('<span class="sr">완료</span>' if i < step else '')
        items.append(f'<li class="{state}"{extra}><span class="dot" aria-hidden="true">{mark}</span>'
                     f'<span class="label">{name}</span>{note}</li>')
    st.html(f'<p class="tis-step-count">{len(STEPS)}단계 중 {step}단계 · {STEPS[step - 1]}</p>'
            f'<ol class="tis-steps" aria-label="진행 단계">{"".join(items)}</ol>')


def flow_targets() -> list[tuple[str, str, Company | None]]:
    """문의·견적 대상: 기존 거래처(있으면 맨 앞) + 담은 후보."""
    targets: list[tuple[str, str, Company | None]] = []
    existing = st.session_state.need['existing']
    if st.session_state.need['journey'] == JOURNEYS[1] and existing:
        targets.append((EXISTING, existing, None))
    targets += [(cid, by_id[cid].name, by_id[cid]) for cid in st.session_state.shortlist]
    return targets


def ai_label(title: str) -> None:
    """AI가 만든 내용 위에 붙이는 제주 주황 'AI' 배지. title은 코드에 적은 고정 문구만 넣는다."""
    st.html(f'<p class="tis-ai-label"><span class="tis-ai">AI</span>{title}</p>')


def show_company(c: Company, prefix: str) -> None:
    with st.container(border=True, key=f'card_{prefix}_{c.id}'):
        st.subheader(c.name)
        st.text(f'{c.industry} · {c.region}')
        st.text('생산품 기록: ' + c.products)
        st.caption(f'출처: {c.source_name} · 데이터 기준일: {c.source_date}')
        st.caption('생산품·주소는 과거 기록입니다. 현재 공급 가능 여부와 연락처는 업체에 확인하세요.')
        chosen = c.id in st.session_state.shortlist
        with st.container(horizontal=True):
            if st.button('상세 확인', key=f'{prefix}_view_{c.id}'):
                record_event(config.database_path, c.id, st.session_state.session_id, 'view')
                st.session_state['detail'] = c.id
            if st.button('담기 취소' if chosen else '비교에 담기', key=f'{prefix}_add_{c.id}', type='secondary' if chosen else 'primary'):
                if chosen:
                    st.session_state.shortlist.remove(c.id)
                    st.rerun()
                elif len(st.session_state.shortlist) >= 5:
                    st.error('후보는 최대 5곳까지 담을 수 있습니다.')
                else:
                    st.session_state.shortlist.append(c.id)
                    record_event(config.database_path, c.id, st.session_state.session_id, 'compare')
                    st.rerun()
        if st.session_state.get('detail') == c.id:
            if c.website:
                st.link_button('등록된 웹사이트 열기', c.website)
            if not c.business_number:
                st.caption('이 자료에는 사업자번호가 없어 국세청 사업자 상태를 조회할 수 없습니다.')
                return
            status = store.read_status(config.database_path, c.id)
            if st.button('국세청 상태 확인', key=f'{prefix}_nts_{c.id}'):
                with st.spinner('사업자 상태 조회 중'):
                    status = refresh_status(config.database_path, c, config)
            if status:
                payload = status.get('payload')
                if payload and payload.get('b_no') == c.business_number:
                    st.text('사업자 상태: ' + payload['label'])
                    st.caption('국세청 조회 성공 시각: ' + str(status['checked_at']))
                if status.get('error'):
                    st.warning(status['error'])
            else:
                st.caption('국세청 상태: 아직 조회하지 않음')
            st.caption('사업자 상태는 품질·신용·납품 능력의 보증이 아닙니다. 성공 결과는 24시간 캐시합니다.')


def run_search() -> None:
    need, scope = st.session_state.need, st.session_state.scope
    region = scope['region'] if scope['region'] != '전체' else ('' if scope['city'] == '전체' else scope['city'])
    request = SearchRequest(query=need['query'], region=region, industry='' if scope['industry'] == '전체' else scope['industry'])
    state = st.session_state
    state.hits, state.questions, state.trace, state.summary, state.search_note = [], [], [], '', ''
    encoder = encoder_at('models/e5') if scope['semantic'] else None
    if scope['use_ai'] and ai_ready:
        try:
            result = run_agent(config, records, request, encoder)
            state.hits, state.questions, state.trace, state.summary = result.hits, result.questions, result.trace, result.summary
        except AgentError as error:
            # AI가 실패해도 도민이 멈추지 않도록 키워드 검색 결과로 이어간다.
            state.search_note = f'{error} 키워드 검색 결과를 대신 보여줍니다.'
            state.hits = search(records, request, encoder)
    else:
        state.hits = search(records, request, encoder)
    state.searched = True


def step_need() -> None:
    need = st.session_state.need
    st.subheader('어떤 거래처가 필요한가요?')
    journey = st.radio('무엇을 하고 싶으세요?', JOURNEYS, index=JOURNEYS.index(need['journey']), horizontal=True, key='w_journey',
                       captions=['처음 거래할 공급처 후보를 찾아요', '지금 거래하는 곳의 견적을 기준으로 다른 곳과 비교해요'])
    query = st.text_input('필요한 품목이나 서비스를 편하게 적어 주세요', value=need['query'], max_chars=200, key='w_query',
                          placeholder='예: 가게 간판을 새로 달고 싶어요 / 택배 박스가 필요해요')
    existing = ''
    if journey == JOURNEYS[1]:
        existing = st.text_input('지금 거래하는 업체 이름', value=need['existing'], max_chars=200, key='w_existing',
                                 help='검색 데이터에 없어도 됩니다. 5단계에서 이 업체의 견적을 비교 기준으로 씁니다.')
    if not records:
        st.info('먼저 왼쪽 메뉴의 데이터 관리에서 기업 데이터를 가져오세요.')
    if nav(None, '다음: 지역 고르기', 'n1'):
        if not query.strip():
            st.error('필요한 품목이나 서비스를 적어 주세요.')
        elif journey == JOURNEYS[1] and not existing.strip():
            st.error('비교할 기존 거래처 이름을 적어 주세요.')
        else:
            st.session_state.need = {'journey': journey, 'query': query.strip(), 'existing': existing.strip()}
            go(2)


def step_scope() -> None:
    scope = st.session_state.scope
    st.subheader('어느 지역에서 찾을까요?')
    st.caption(f"찾는 품목: {st.session_state.need['query']}")
    cities = ['전체'] + sorted({c.region.split()[0] for c in records if c.region.strip()})
    city = st.radio('시', cities, index=cities.index(scope['city']) if scope['city'] in cities else 0, horizontal=True, key='w_city')
    regions = ['전체'] + sorted({c.region for c in records if city == '전체' or c.region.split()[0] == city})
    region = st.selectbox('읍·면·동 (모르면 전체)', regions, key='w_region',
                          index=regions.index(scope['region']) if scope['region'] in regions else 0)
    use_ai = st.toggle('AI Agent가 업종 분류와 지역 분포를 확인하며 찾기', value=scope['use_ai'] and ai_ready,
                       disabled=not ai_ready, key='w_ai')
    if not ai_ready:
        st.caption('AI Agent를 쓰려면 API 키와 외부 전송 허용 설정이 필요합니다. 지금은 키워드 검색으로 찾습니다.')
    with st.expander('업종을 알고 있다면 (선택)'):
        industries = ['전체'] + sorted({c.industry for c in records})
        industry = st.selectbox('업종', industries, key='w_industry',
                                index=industries.index(scope['industry']) if scope['industry'] in industries else 0)
        semantic = st.checkbox('로컬 의미 검색 함께 사용', value=scope['semantic'], key='w_semantic',
                               help='선택 설치 및 models/e5 모델 준비가 필요합니다. 자동 다운로드하지 않습니다.')
    if nav(1, '후보 찾기', 'n2'):
        st.session_state.scope = {'city': city, 'region': region, 'industry': industry, 'use_ai': use_ai, 'semantic': semantic}
        try:
            with st.spinner('근거를 확인하며 찾는 중'):
                run_search()
            go(3)
        except (ValueError, OSError):
            st.error('검색 조건 또는 로컬 모델을 확인하세요. 의미 검색을 끄고 다시 시도할 수 있습니다.')


def step_candidates() -> None:
    state = st.session_state
    scope = state.scope
    place = scope['region'] if scope['region'] != '전체' else scope['city']
    st.subheader('비교할 후보를 고르세요')
    st.caption(f"'{state.need['query']}' · 지역 {place} · 최대 5곳까지 담을 수 있습니다.")
    if state.search_note:
        st.warning(state.search_note)
    if state.summary:
        with st.container(border=True, key='ai_summary'):
            ai_label('Agent 탐색 요약')
            st.text(state.summary)
            st.caption('요약의 숫자는 Agent 도구가 이 PC의 데이터에서 센 값만 허용합니다. 판단은 아래 근거와 함께 확인하세요.')
    for question in state.questions:
        st.text('추가로 확인할 점: ' + question)
    if state.trace:
        with st.expander('Agent가 수행한 단계', expanded=True):
            for number, line in enumerate(trace_lines(state.trace), start=1):
                st.text(f'{number}. {line}')
            st.json(state.trace, expanded=False)
    if state.searched and not state.hits:
        st.info('조건에 맞는 근거를 찾지 못했습니다. 이전 단계에서 지역을 넓히거나, 첫 단계에서 품목을 짧게 적어 보세요.')
    for hit in state.hits:
        if hit.company.id in by_id:
            st.caption(hit.method + ' · ' + ' / '.join(hit.reasons))
            show_company(by_id[hit.company.id], 'search')
    names = [by_id[cid].name for cid in state.shortlist]
    st.caption('담은 후보: ' + (', '.join(names) if names else '아직 없음'))
    if nav(2, '다음: 문의 준비', 'n3'):
        if not state.shortlist:
            st.error('비교할 후보를 1곳 이상 담아 주세요.')
        else:
            go(4)


def step_inquiry() -> None:
    state = st.session_state
    cond = state.conditions
    targets = flow_targets()
    st.subheader('견적 요청 조건을 한 번만 적으세요')
    st.caption('적은 조건으로 업체마다 같은 양식의 문의 초안을 만들고, 다음 단계 견적 입력 칸에도 그대로 채웁니다. 자동 발송하지 않습니다.')
    st.caption('문의 대상: ' + ', '.join(name for _, name, _ in targets))
    with st.form('conditions_form'):
        item = st.text_input('품목 (업체에 보낼 짧은 이름)', value=cond.get('item', ''), key='w_item',
                             placeholder=f"예: LED 간판 · 처음 적은 내용: {state.need['query']}")
        left, middle, right = st.columns(3)
        spec = left.text_input('규격', value=cond.get('specification', ''), key='w_spec', placeholder='예: 1200x600 LED')
        quantity = middle.text_input('수량', value=cond.get('quantity', ''), key='w_quantity', placeholder='예: 500')
        unit = right.text_input('단위', value=cond.get('unit', '개'), key='w_unit')
        notes = st.text_area('추가 요청 (희망 납기, 설치·배송 여부 등)', value=cond.get('notes', ''), key='w_notes')
        use_ai = st.checkbox('AI가 업체의 등록 업종·생산품을 보고 확인 질문을 덧붙이기', value=ai_ready, disabled=not ai_ready, key='w_inquiry_ai')
        create = st.form_submit_button('조건 저장하고 문의 초안 만들기', type='primary', key='create_inquiry')
    if create:
        try:
            if Decimal(quantity) <= 0 or not Decimal(quantity).is_finite():
                raise ValueError()
            drafts, note = {}, ''
            for key, name, company in targets:
                questions: list[str] = []
                if use_ai:
                    try:
                        with st.spinner(f'{name} 확인 질문을 만드는 중'):
                            questions = inquiry_questions(config, {'item': item, 'specification': spec, 'quantity': quantity,
                                                                   'unit': unit, 'notes': notes}, company)
                    except AgentError as error:
                        note = f'{error} 일부 초안은 고정 양식으로 만들었습니다.'
                drafts[key] = inquiry(name, item, spec, quantity, unit, notes, questions)
            state.conditions = {'item': item, 'specification': spec, 'quantity': quantity, 'unit': unit, 'notes': notes}
            state.drafts, state.inquiry_note = drafts, note
            st.rerun()
        except (ValueError, ArithmeticError):
            st.error('품목·규격·단위와 0보다 큰 수량을 입력하세요.')
    if state.inquiry_note:
        st.warning(state.inquiry_note)
    drafts = {key: text for key, text in state.drafts.items() if key in {t[0] for t in targets}}
    if drafts:
        names = {key: name for key, name, _ in targets}
        for tab, (key, text) in zip(st.tabs([names[key] for key in drafts]), drafts.items()):
            with tab:
                st.text(text)
                st.download_button('이 초안 다운로드', text, f'거래잇수다_문의_{names[key]}.txt', 'text/plain', key=f'download_inquiry_{key}')
        st.download_button('초안 모두 한 파일로 받기', '\n\n----------\n\n'.join(drafts.values()), '거래잇수다_문의_전체.txt',
                           'text/plain', key='download_inquiry_all')
    if nav(3, '다음: 받은 견적 입력', 'n4'):
        if not state.conditions:
            st.error('요청 조건을 먼저 저장하세요. 다음 단계 견적 입력에 같은 조건을 채웁니다.')
        else:
            go(5)


def quote_form(target: str, name: str, saved_by_id: dict[str, Quote]) -> None:
    state = st.session_state
    existing_id = state.flow_quotes.get(target)
    extracted = state.extracted.get('values', {}) if state.extracted.get('target') == target else {}
    if extracted:
        seed = {**state.conditions, **extracted}
    elif existing_id in saved_by_id:
        seed = saved_by_id[existing_id].model_dump(mode='json')
    else:
        seed = dict(state.conditions)
    prefix = f'q_{target}_{state.extraction_version}_{existing_id or "new"}'

    def field(container, label: str, name: str, default: str = '', help: str | None = None):
        value = seed.get(name)
        return container.text_input(label, value=str(default if value is None else value), key=f'{prefix}_{name}', help=help)

    # KRDS 신청서 작성 패턴: 필수 칸은 숨기지 않고 섹션 제목을 두며, 도움말은 화면 위가 아니라 입력 칸 옆(툴팁)에 둔다.
    with st.form(f'quote_form_{target}'):
        company_name = field(st, '업체명', 'company_name', name) if target == OTHER else name
        st.markdown('#### ① 요청 조건')
        st.caption('4단계에서 적은 조건을 채웠어요. 견적서 내용과 다르면 고쳐 주세요.')
        a, b, c, d = st.columns([2, 2, 1, 1])
        item = field(a, '품목', 'item')
        specification = field(b, '규격', 'specification', help='크기·재질·색 등 업체가 견적에 적은 사양')
        quantity = field(c, '수량', 'quantity')
        unit = field(d, '단위', 'unit', help='개, 박스, 장, m² 처럼 수량을 세는 단위')
        st.markdown('#### ② 금액')
        st.caption('모르는 금액은 빈칸으로 두세요. 0은 무료로 확인된 경우에만 넣어요.')
        a, b, c = st.columns(3)
        unit_price = field(a, '단가', 'unit_price', help='단위 1개당 가격. 견적서의 숫자만 넣어요(쉼표 없이).')
        tax_options = ['미확인', '포함', '별도']
        tax = b.selectbox('단가에 부가세 포함?', tax_options, key=f'{prefix}_tax',
                          index=tax_options.index({None: '미확인', True: '포함', False: '별도'}[seed.get('tax_included')]),
                          help='견적서에 "부가세 포함"이면 포함, "부가세 별도"이면 별도를 고르세요.')
        tax_rate = c.text_input('별도 세율 (%)', key=f'{prefix}_rate', help='부가세 별도일 때만 넣어요. 보통 10',
                                value=str(Decimal(str(seed['tax_rate'])) * 100) if seed.get('tax_rate') is not None else '')
        a, b, c = st.columns(3)
        shipping = field(a, '배송비 (세금 포함)', 'shipping', help='세금까지 더한 최종 배송비. 무료로 확인됐으면 0, 모르면 빈칸')
        extra_cost = field(b, '추가 비용 (세금 포함)', 'extra_cost', help='설치비·디자인비 등 단가 밖의 비용 합계. 없으면 0, 모르면 빈칸')
        currency = field(c, '통화', 'currency', 'KRW', help='원화는 KRW')
        st.markdown('#### ③ 거래 조건과 근거')
        a, b, c, d = st.columns(4)
        minimum_order = field(a, '최소 주문 수량', 'minimum_order', help='업체가 받는 가장 적은 주문량. 요청 수량보다 크면 비교표에 표시돼요.')
        lead_days = field(b, '납기 (일)', 'lead_days', help='주문 후 받기까지 걸리는 날 수')
        issued_at = field(c, '견적 발행일 (YYYY-MM-DD)', 'issued_at')
        valid_until = field(d, '유효기간 (YYYY-MM-DD)', 'valid_until', help='이 날짜가 지나면 견적 가격이 바뀔 수 있어요.')
        source_name = field(st, '견적 근거 (견적서 파일명·담당자 회신일 등)', 'source_name', '사용자 입력',
                            help='나중에 다시 확인할 수 있게 견적을 받은 경로를 적어요.')
        confirmed = st.checkbox('견적서 원문과 대조해 입력값을 확인했습니다', value=bool(seed.get('confirmed', False)), key=f'{prefix}_confirmed')
        save = st.form_submit_button('이 업체 견적 저장', type='primary', key='save_quote')
    if save:
        try:
            qid = existing_id if existing_id in saved_by_id else str(uuid4())
            quote = Quote(id=qid, company_id=target if target in by_id else f'manual-{qid}', company_name=company_name,
                          item=item, specification=specification, unit=unit, quantity=quantity, unit_price=unit_price or None,
                          currency=currency, tax_included={'미확인': None, '포함': True, '별도': False}[tax],
                          tax_rate=Decimal(tax_rate) / 100 if tax_rate else None, shipping=shipping or None,
                          extra_cost=extra_cost or None, minimum_order=minimum_order or None, lead_days=lead_days or None,
                          issued_at=issued_at or None, valid_until=valid_until or None, source_name=source_name, confirmed=confirmed)
            store.save_quotes(config.database_path, [quote])
            # '다른 업체'는 저장할 때마다 새 견적이 되도록 대상 키를 견적 ID로 바꿔 둔다.
            state.flow_quotes[target if target != OTHER else f'{OTHER}-{qid}'] = qid
            state.extracted = {}
            state.flash = f'{company_name} 견적을 저장했습니다.'
            st.rerun()
        except (ValueError, ArithmeticError, KeyError):
            st.error('입력값을 확인하세요. 필수 항목·숫자·통화 코드·날짜 순서가 올바르지 않습니다.')


def step_quotes() -> None:
    state = st.session_state
    saved_by_id = {q.id: q for q in store.quotes(config.database_path)}
    state.flow_quotes = {k: v for k, v in state.flow_quotes.items() if v in saved_by_id}
    targets = flow_targets()
    names = {key: name for key, name, _ in targets}
    for key, qid in state.flow_quotes.items():
        names.setdefault(key, saved_by_id[qid].company_name)
    st.subheader('받은 견적을 업체별로 입력하세요')
    st.caption('업체를 하나씩 골라 견적을 저장합니다. 조건이 같아야 다음 단계에서 차액을 계산할 수 있습니다.')
    # 화면에 보이는 이름을 그대로 선택지로 쓴다(이름이 같으면 번호를 붙여 구분). 입력 여부는 아래 캡션에 따로 보여 준다.
    labels: dict[str, str] = {}
    for key in [*names, OTHER]:
        label = '+ 다른 업체' if key == OTHER else names[key]
        while label in labels:
            label += ' (2)'
        labels[label] = key
    chosen = st.radio('견적 업체', list(labels), horizontal=True, key='w_quote_target')
    target = labels.get(chosen or '', next(iter(labels.values())))
    if target == EXISTING:
        st.caption('기존 거래처 견적은 6단계에서 비교 기준이 됩니다.')
    with st.expander('견적서 텍스트·PDF가 있으면 AI가 칸을 채워 드려요'):
        st.caption('연락처·개인정보를 지우고 외부 전송 가능한 자료만 사용하세요. 채운 값은 반드시 원문과 대조하세요.')
        with st.form('extract_form'):
            upload = st.file_uploader('견적 파일 (선택)', type=['txt', 'pdf'], key='quote_file')
            text = st.text_area('또는 견적 원문 붙여넣기', key='quote_text', max_chars=20000)
            extract = st.form_submit_button('AI로 칸 채우기', key='extract_submit', disabled=not ai_ready)
        if extract:
            try:
                raw = quote_text(upload.getvalue(), upload.name) if upload else text
                with st.spinner('견적 추출 중'):
                    draft = extract_quote(config, raw)
                state.extracted = {'target': target, 'values': draft.model_dump(mode='json', exclude_none=True)}
                state.extraction_version += 1
                state.flash = '추출값을 채웠습니다. 원문과 대조하고 빠진 조건을 입력하세요.'
                st.rerun()
            except AgentError as error:
                st.error(str(error))
    quote_form(target, names.get(target, ''), saved_by_id)
    if target in state.flow_quotes and st.button('이 업체 견적 삭제', key='delete_quote'):
        store.delete_quote(config.database_path, state.flow_quotes.pop(target))
        state.flash = '견적을 삭제했습니다.'
        st.rerun()
    done = [names[k] for k in state.flow_quotes]
    st.caption('입력한 견적: ' + (', '.join(done) if done else '아직 없음'))
    if nav(4, '다음: 비교 결과 보기', 'n5'):
        if not state.flow_quotes:
            st.error('견적을 1개 이상 저장하세요.')
        else:
            go(6)


def step_result() -> None:
    state = st.session_state
    saved_by_id = {q.id: q for q in store.quotes(config.database_path)}
    flow_ids = [qid for qid in state.flow_quotes.values() if qid in saved_by_id]
    st.subheader('같은 조건으로 비교한 결과')
    st.caption('빈 금액은 미확인입니다. 품목·규격·단위·수량·통화가 같고 비용이 모두 확인된 견적만 차액을 계산합니다.')
    others = [qid for qid in saved_by_id if qid not in flow_ids]
    extra: list[str] = []
    if others:
        with st.expander('이전에 저장한 견적도 함께 비교하기'):
            extra = st.multiselect('추가할 견적', others, key='w_extra_quotes',
                                   format_func=lambda qid: saved_by_id[qid].company_name + ' / ' + saved_by_id[qid].item)
    selected = flow_ids + extra
    if not selected:
        st.info('비교할 견적이 없습니다. 이전 단계에서 견적을 저장하세요.')
    elif len(selected) > 6:
        st.error('견적은 최대 6개까지 비교할 수 있습니다.')
    else:
        default = state.flow_quotes.get(EXISTING, selected[0])
        baseline_id = st.selectbox('비교 기준 견적', selected, index=selected.index(default) if default in selected else 0,
                                   format_func=lambda qid: saved_by_id[qid].company_name, key='baseline_id')
        rows = compare([saved_by_id[qid] for qid in selected], baseline_id)
        table = rows_for_export(rows)
        st.dataframe(table, hide_index=True, alt='견적 총액과 비교 제한 조건')
        st.caption('차액 = 후보 총액 − 기준 총액. 조건이 다르거나 비용이 미확인인 견적은 차액 비교에서 제외합니다.')
        with st.container(horizontal=True):
            st.download_button('비교 보고서 (HTML)', html_report(rows, baseline_id, records), '거래잇수다_비교.html', 'text/html', key='download_html')
            st.download_button('비교표 (CSV)', csv_report(rows), '거래잇수다_비교.csv', 'text/csv', key='download_csv')
        # 견적 내용이나 기준이 바뀌면 이전 해설을 보여주지 않는다.
        advice_key = repr((table, baseline_id))
        if st.button('AI 비교 해설 받기', key='explain_compare', disabled=not ai_ready):
            try:
                with st.spinner('비교표를 해설하는 중'):
                    state.advice = (advice_key, explain_comparison(config, table, saved_by_id[baseline_id].company_name))
            except AgentError as error:
                st.error(str(error))
        if state.advice and state.advice[0] == advice_key:
            result = state.advice[1]
            with st.container(border=True, key='ai_advice'):
                ai_label('비교 해설')
                st.caption('숫자는 위 비교표 값만 허용합니다. 결정은 업체 확인 후 직접 하세요.')
                st.text(result.summary)
                for check in result.checks:
                    st.text('확인할 점: ' + check)
                for label, text in [('유지', result.keep), ('병행', result.parallel), ('전환', result.switch)]:
                    if text:
                        st.text(f'{label} 검토 조건: {text}')
    nav(5, None, 'n6')
    if st.button('처음부터 새로 찾기', key='restart', icon=':material/restart_alt:'):
        for key, value in deepcopy(FLOW_DEFAULTS).items():
            st.session_state[key] = value
        go(1)


def page_popular() -> None:
    st.subheader('최근 30일, 이용자가 관심을 보인 업체')
    st.caption('상세 보기·비교 선택에서 수집한 세션별·일별 관심 수입니다. 같은 세션의 같은 날 반복 클릭은 중복 처리합니다. 품질·신용 순위가 아닙니다.')
    prune_events(config.database_path)
    region = st.selectbox('관심 업체 지역', ['전체'] + sorted({c.region for c in records}), key='popular_region')
    allowed = {c.id for c in records if region == '전체' or c.region == region}
    rankings = popular(config.database_path, allowed_ids=allowed)
    if not rankings:
        st.info('아직 집계된 관심 기록이 없습니다. 가상 수치를 채우지 않습니다.')
    for rank in rankings:
        c = by_id[rank['company_id']]
        if config.nts_key and config.allow_external_data and c.business_number:
            refresh_status(config.database_path, c, config)
        st.caption(f'관심 {rank["interest_count"]}회 · 상세 보기 {rank["views"]}회 · 비교 선택 {rank["comparisons"]}회')
        show_company(c, 'popular')
    st.caption('사업자번호가 있는 업체만 이 화면을 여는 동안 캐시 주기에 따라 국세청 상태를 갱신합니다. 앱이 꺼져 있을 때나 생산품 정보는 자동 갱신하지 않습니다.')

def page_data() -> None:
    st.subheader('기업 데이터 가져오기')
    st.caption(f'AI 설정: {config.provider} / {config.model}' + ('' if ai_ready else ' · API 키 또는 외부 전송 허용이 없어 AI가 꺼져 있습니다')
               + ' · 이 PC 한 사람용입니다. 공용 PC에서는 사용 후 견적을 삭제하세요.')
    st.info('명세서가 아닌 실제 기업 행이 필요합니다. 원본 반출·가공·외부 전송 허용 여부는 각각 확인해야 합니다.')
    st.caption('필수 열: name/기업명, industry/업종명, products/주요생산품, region/주소_읍면동. 데이터 기준일은 source_date/데이터 기준일 또는 아래 공통 기준일로 입력합니다.')
    st.caption('제주데이터허브 「제주특별자치도 상가(상권) 정보」 CSV는 그대로 가져올 수 있습니다. 상호명·상권업종중분류명을 업체명·업종으로, '
               '상권업종소분류명·표준산업분류명을 생산품으로, 시군구명·행정동명을 지역으로 씁니다. 파일에 기준일이 없으니 공통 기준일(수집일)을 입력하세요.')
    with st.form('import_form'):
        upload = st.file_uploader('기업 데이터 CSV 또는 XLSX', type=['csv', 'xlsx'], key='company_file')
        source_name = st.text_input('정확한 데이터셋명·제공기관', key='source_name')
        source_date = st.text_input('공통 데이터 기준일 (파일에 없을 때만, YYYY-MM-DD)', key='source_date')
        sheet = st.text_input('XLSX 시트 이름 또는 번호', value='0', key='sheet')
        rights = st.checkbox('이 PC에서 사용·저장할 수 있도록 승인된 실제 기업 자료임을 확인했습니다', key='import_rights')
        submitted = st.form_submit_button('검증 후 가져오기', key='import_submit')
    if submitted:
        try:
            if not upload or not rights:
                raise ValueError('파일과 데이터 이용 권한 확인이 필요합니다.')
            raw = upload.getvalue()
            parsed = parse_file(raw, upload.name, source_name, date.fromisoformat(source_date) if source_date else None,
                                int(sheet) if sheet.isdigit() else sheet)
            import_companies(config.database_path, parsed.records, raw, source_name)
            st.session_state.hits, st.session_state.trace = [], []
            st.session_state['import_report'] = [
                {'제외 사유': reason, '행 수': len(rows), '원본 행 번호 (앞 20개)': ', '.join(map(str, rows[:20]))}
                for reason, rows in parsed.skipped.items()]
            st.session_state.flash = (f'{len(parsed.records):,}개 기업을 검증해 가져왔습니다.'
                                      + (f' {parsed.skipped_count:,}행은 제외했습니다. 아래 제외 내역을 확인하세요.' if parsed.skipped else ''))
            st.rerun()
        except (ValueError, OSError) as error:
            st.error(str(error) if not isinstance(error, ValidationError) else '데이터 형식을 확인하세요.')
    if st.session_state.get('import_report'):
        st.caption('최근 가져오기에서 제외한 행입니다. 데이터 활용 명세의 결측·제외 행 수로 기록하세요.')
        st.dataframe(st.session_state.import_report, hide_index=True, alt='가져오기에서 제외한 행과 사유')
    if st.button('가상 데모 4곳 불러오기', key='load_demo', disabled=bool(records)):
        import_companies(config.database_path, demo_companies(), b'trade-itsuda-synthetic-v1', '가상 기능 검증 데이터')
        st.session_state.flash = '가상 데모를 불러왔습니다. 거래처 찾기에서 라벨·박스·유리병을 검색하세요.'
        st.rerun()
    st.caption('가상 데모는 빈 데이터베이스에서만 불러옵니다. 실제 데이터와 데모는 별도 DB로 운영하세요 (README 참고).')
    history = store.import_history(config.database_path)
    if history:
        st.dataframe(history, hide_index=True, alt='원본 파일 해시와 가져오기 이력')
    st.caption('API 키는 .env에서만 설정하고 화면·보고서·Git에 포함하지 않습니다. 기본 저장소와 업로드 자료는 Git 추적에서 제외됩니다.')


# 가운데 흰 화면 카드 안에 현재 메뉴의 화면을 그린다.
with st.container(key='screen'):
    if page == '거래처 찾기':
        current = st.session_state.step
        header(current)
        {1: step_need, 2: step_scope, 3: step_candidates, 4: step_inquiry, 5: step_quotes, 6: step_result}[current]()
    elif page == '최근 관심 업체':
        page_popular()
    else:
        page_data()
