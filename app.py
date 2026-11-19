from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import re
from html import escape
from urllib.parse import quote
from uuid import uuid4

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from pydantic import ValidationError

from trade_itsuda import store
from trade_itsuda.agent import (AgentError, explain_comparison, extract_quote, inquiry_questions, quote_text, run_agent,
                                trace_lines)
from trade_itsuda.business import lookup_status, refresh_status
from trade_itsuda.comparison import Comparison, compare
from trade_itsuda.config import settings
from trade_itsuda.exporting import csv_report, html_report, inquiry, rows_for_export
from trade_itsuda.ingest import demo_companies, import_companies, parse_file
from trade_itsuda.models import Company, Quote, SearchRequest
from trade_itsuda.popularity import popular, prune_events, record_event
from trade_itsuda.reply import parse_reply
from trade_itsuda.retrieval import load_encoder, search

STEPS = ['필요 품목', '지역', '후보 고르기', '문의 준비', '견적 입력', '비교 결과']
JOURNEYS = ['새 거래처 찾기', '기존 거래처와 비교']
EXISTING = 'existing'
OTHER = 'other'
# 배경: 하늘빛 그라데이션 위에 겹친 오름(파랑) · 한라산 숲(초록) · 바다 물결을 벡터로 그린다.
# SVG라 어떤 해상도에서도 선명하고, 화면 너비에 맞춰 늘거나 좁은 화면에서는 가운데를 기준으로 잘린다.
BACKGROUND_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 360'>"
    "<path d='M0 250C180 205 330 168 500 200C620 222 700 150 850 138C1010 126 1120 214 1260 206"
    "C1350 201 1400 182 1440 172L1440 360L0 360Z' fill='#cfe0fb' fill-opacity='0.55'/>"
    "<path d='M0 292C150 258 300 246 450 266C610 288 710 238 870 232C1050 226 1170 284 1440 256"
    "L1440 360L0 360Z' fill='#cdebd9' fill-opacity='0.6'/>"
    "<path d='M0 328C120 314 240 342 360 328S600 314 720 328S960 342 1080 328S1320 314 1440 328"
    "L1440 360L0 360Z' fill='#b1cefb' fill-opacity='0.5'/>"
    "<path d='M0 342C120 330 240 354 360 342S600 330 720 342S960 354 1080 342S1320 330 1440 342' "
    "fill='none' stroke='#ffffff' stroke-opacity='0.75' stroke-width='2'/>"
    "</svg>")

st.set_page_config(page_title='거래잇수다', page_icon=':material/handshake:', layout='centered',
                   initial_sidebar_state='collapsed')
# KRDS(범정부 디자인 시스템) 표준형 색상: primary-50 #256ef4, primary-5 #ecf2fe, gray-20 #cdd1d5, gray-50 #6d7882.
# 테마 색·글꼴은 .streamlit/config.toml, 여기서는 앱 틀(상단 앱 바·화면 카드·하단 버튼 바)과
# 기본 위젯에 없는 단계 표시기·목적 카드 모양을 정한다.
st.html('''<style>
/* 앱 틀: Streamlit 기본 머리줄·메뉴·사이드바를 숨기고, 회색 바탕 위 가운데 흰 화면 카드로 보이게 한다. */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], footer { display: none !important; }
[data-testid="stMain"], [data-testid="stBottom"] > div { background: transparent; }
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
.st-key-screen { background: rgba(255, 255, 255, 0.93); backdrop-filter: blur(8px); border-radius: 20px;
  padding: 28px 32px 8px; box-shadow: 0 1px 2px rgba(30, 33, 36, 0.06), 0 12px 32px rgba(30, 33, 36, 0.08); }
[class*="st-key-navbar_"] { background: #fff; padding: 12px 0 16px; border-top: 1px solid #e6e8ea; }
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-navbar_"]) { background: #fff; margin-top: 8px; }
/* 좁은 화면에서도 이전·다음 버튼은 한 줄에 둔다(Streamlit 기본은 열을 세로로 쌓음). */
[class*="st-key-navbar_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
[class*="st-key-navbar_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
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
.st-key-w_journey div[role="radiogroup"] > div { flex: 1 1 240px; padding: 16px 20px; border: 1px solid #e6e8ea;
  border-radius: 16px; background: #fff; margin: 0; cursor: pointer; }
.st-key-w_journey div[role="radiogroup"] > div:has(input:checked) { border-color: #256ef4; background: #ecf2fe;
  box-shadow: inset 0 0 0 1px #256ef4; }
.st-key-w_journey div[role="radiogroup"] > div label { font-weight: 700; }
@media (max-width: 640px) { .tis-steps .label { display: none; } }
/* 글마다 상자를 두지 않는다. 구획은 제목·얇은 구분선·여백·왼쪽 세로선으로 나눈다. */
[class*="st-key-card_"] { gap: 4px; padding: 18px 0 16px; border-bottom: 1px solid #e6e8ea; }
.tis-row-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 12px; }
.tis-row-head strong { font-size: 1.15rem; color: #1e2124; }
.tis-row-head span { font-size: 0.85rem; color: #6d7882; }
.tis-row-note { margin: 2px 0 0; font-size: 0.8rem; color: #0b50d0; }
/* 상자 없는 구획(설정 화면 방식): 왼쪽 제목 열 + 오른쪽 입력, 구획 사이는 가는 선 한 줄 */
[class*="st-key-sec_"] { border-top: 1px solid #e6e8ea; padding: 18px 0 6px; }
.tis-sec-title { font-weight: 700; color: #1e2124; margin: 0 0 4px; font-size: 1rem; }
.tis-sec-note { font-size: 0.8rem; color: #6d7882; margin: 0; line-height: 1.5; }
@media (max-width: 640px) { [class*="st-key-sec_"] [data-testid="stHorizontalBlock"] { gap: 12px !important; } }
[data-testid="stAlertContainer"] { background: transparent !important; border-radius: 0 !important;
  border-left: 3px solid currentColor; padding: 6px 0 6px 14px !important; }
/* 펼침 영역은 상자 대신 글자만 있는 '› 열기' 줄로 보이게 한다. */
[data-testid="stExpander"] details { border: none !important; border-radius: 0 !important; background: transparent !important; }
[data-testid="stExpander"] summary { padding-left: 0 !important; color: #0b50d0; background: transparent !important; }
[data-testid="stExpander"] summary:hover { color: #083891; }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding-left: 0 !important; padding-right: 0 !important; }
/* 제주 포인트: AI가 만든 내용에만 제주 주황(#b34f00, 흰 배경 대비 약 7:1) 세로선과 배지를 쓴다.
   KRDS 강조색 규칙대로 화면의 5% 이하. */
/* 문의 초안: 코드 상자 대신 읽기 쉬운 본문 글꼴로 */
[data-testid="stCode"] pre, [data-testid="stCode"] code { font-family: inherit !important; font-size: 0.95rem !important; line-height: 1.7 !important; }
.st-key-ai_summary, .st-key-ai_advice, .st-key-ai_extract_note { border-left: 3px solid #b34f00; padding: 2px 0 2px 16px; margin: 4px 0 8px; }
.tis-ai-label { margin: 0; font-weight: 700; color: #1e2124; display: flex; align-items: center; gap: 8px; }
.tis-ai { display: inline-block; background: #b34f00; color: #fff; font-size: 0.75rem; font-weight: 700;
  line-height: 1; padding: 4px 8px; border-radius: 999px; letter-spacing: 0.02em; }
/* 하단 바의 '담은 후보 2/5' 같은 상태 알약 */
.tis-pill { display: inline-block; padding: 6px 12px; border-radius: 999px; background: #ecf2fe; color: #0b50d0;
  font-size: 0.85rem; font-weight: 700; white-space: nowrap; }
/* Agent가 실제로 한 일: 화살표로 이어진 단계 */
.tis-trace { list-style: none; counter-reset: step; display: flex; flex-direction: column; gap: 6px; padding: 0; margin: 10px 0 4px; }
.tis-trace li { counter-increment: step; display: flex; align-items: baseline; gap: 8px; font-size: 0.85rem; color: #1e2124; }
.tis-trace li::before { content: counter(step); flex: none; width: 20px; height: 20px; border-radius: 50%; background: #b34f00; color: #fff;
  font-size: 0.72rem; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; transform: translateY(-1px); }
.tis-source { font-size: 0.8rem; color: #6d7882; margin: 4px 0 0; }
/* 6단계 결론: 업체별 총액 카드 */
.tis-verdict { font-size: 1.05rem; margin: 4px 0 12px; }
.tis-verdict b { color: #228738; }
.tis-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0; margin: 8px 0 12px;
  border-top: 1px solid #e6e8ea; border-bottom: 1px solid #e6e8ea; }
/* 카드 상자 대신 세로 가는 선으로 나눈 숫자 열. 가장 싼 곳은 테두리 대신 초록 숫자로 강조한다. */
.tis-card { padding: 16px 20px; border-left: 1px solid #e6e8ea; }
.tis-card:first-child { border-left: none; padding-left: 0; }
.tis-card.best .total { color: #1a7f37; }
@media (max-width: 640px) {
  .tis-card { border-left: none; padding-left: 0; border-top: 1px solid #e6e8ea; }
  .tis-card:first-child { border-top: none; }
}
.tis-card .name { font-weight: 700; color: #1e2124; }
.tis-card .total { font-size: 1.6rem; font-weight: 800; color: #1e2124; margin: 6px 0; letter-spacing: -0.01em; }
.tis-card .total.unknown { font-size: 1.05rem; color: #6d7882; font-weight: 700; }
.tis-badge { display: inline-block; font-size: 0.78rem; font-weight: 700; padding: 3px 8px; border-radius: 999px; }
.tis-badge.base { background: #e6e8ea; color: #464c53; }
.tis-badge.cheaper { background: #e5f4e4; color: #1a6b2c; }
.tis-badge.pricier { background: #fbebeb; color: #b42318; }
.tis-badge.blocked { background: #f9eeda; color: #7a5200; }
.tis-nts { margin: 8px 0 0; font-size: 0.8rem; color: #464c53; }
.tis-card ul { margin: 10px 0 0; padding: 0; list-style: none; font-size: 0.8rem; color: #464c53; }
.tis-card li::before { content: "☐ "; color: #9e6a00; }
.tis-ai-cols h5 { font-size: 0.9rem; margin: 0 0 4px; }
.tis-checks { margin: 6px 0 10px; padding-left: 0; list-style: none; }
.tis-checks li { margin: 2px 0; }
.tis-checks li::before { content: "☐ "; color: #b34f00; }
/* 직접 그린 목록은 Streamlit 기본 들여쓰기를 쓰지 않는다(본문 왼쪽 선에 맞춘다). */
:is(.tis-saved, .tis-trace, .tis-checks, .tis-card ul) { margin-left: 0 !important; padding-left: 0 !important; }
:is(.tis-saved, .tis-trace, .tis-checks, .tis-card ul) > li { margin-left: 0 !important; }
/* 5단계: 업체별 저장 상태 */
.tis-saved { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; padding: 0; list-style: none; }
.tis-saved li { font-size: 0.8rem; padding: 3px 10px; border-radius: 999px; background: #f4f5f6; color: #6d7882; }
.tis-saved li.ok { background: #e5f4e4; color: #1a6b2c; }
</style>''')
# 배경은 화면(뷰포트) 크기를 기준으로 그린다: 그라데이션은 화면 전체, 오름·바다 그림은 화면 너비(최소 1100px)에 맞춰
# 아래에 붙이고 스크롤해도 고정한다. 해상도와 상관없이 선명하도록 모두 CSS 그라데이션과 SVG(벡터)다.
st.html('<style>.stApp { background-color: #f3f6fb; background-repeat: no-repeat; background-attachment: fixed;'
        f' background-image: url("data:image/svg+xml,{quote(BACKGROUND_SVG)}"),'
        ' radial-gradient(circle 38vmax at 92% 4%, rgba(255, 214, 170, 0.55), rgba(255, 214, 170, 0)),'
        ' radial-gradient(circle 46vmax at 6% 0%, rgba(177, 206, 251, 0.6), rgba(177, 206, 251, 0)),'
        ' linear-gradient(180deg, #eaf2fe 0%, #f5f8fc 55%, #eef6f1 100%);'
        ' background-position: center bottom, 0 0, 0 0, 0 0;'
        ' background-size: max(100%, 1100px) auto, 100% 100%, 100% 100%, 100% 100%; }</style>')
try:
    config = settings()
    store.initialize(config.database_path)
except (ValueError, OSError):
    st.error('환경 설정 또는 데이터 폴더를 확인하세요. README의 설치 절차를 참고하세요.')
    st.stop()
ai_configured = bool(config.llm_key and config.allow_external_data)

# 단계 사이에 유지할 값. 위젯 값은 화면을 떠나면 지워지므로 '다음'을 누를 때 여기에 옮겨 둔다.
FLOW_DEFAULTS = {
    'step': 1,
    'need': {'journey': JOURNEYS[0], 'query': '', 'existing': '', 'answers': []},
    'scope': {'city': '전체', 'region': '전체', 'industry': '전체', 'use_ai': True, 'semantic': False},
    'hits': [], 'questions': [], 'trace': [], 'summary': '', 'search_note': '', 'searched': False,
    'shortlist': [], 'conditions': {}, 'drafts': {}, 'inquiry_note': '',
    'flow_quotes': {}, 'extracted': {}, 'extraction_version': 0, 'advice': None, 'search_log': {}, 'nts': {},
}
for key, value in {'session_id': str(uuid4()), 'flash': '', 'ai_used': 0, **deepcopy(FLOW_DEFAULTS)}.items():
    st.session_state.setdefault(key, value)
# 비용 관리: 세션당 AI 작업 수 한도. 다 쓰면 AI 기능을 끄고 키워드 검색·직접 입력으로 이어간다('처음부터'로 초기화되지 않음).
ai_limit_reached = ai_configured and st.session_state.ai_used >= config.ai_session_limit
ai_ready = ai_configured and not ai_limit_reached


def count_ai(times: int = 1) -> None:
    st.session_state.ai_used += times


@st.cache_resource(max_entries=2, show_spinner='제주 상가 데이터 57,347곳을 불러오는 중입니다. 서버를 켠 뒤 처음 한 번은 1분 가까이 걸릴 수 있어요.')
def load_companies(path: str, version: int) -> list[Company]:
    # cache_data는 클릭(재실행)마다 5만 7천 곳을 복사(unpickle, 개발 PC 약 0.9초)한다. 목록은 고치지 않으므로 한 벌을 함께 쓴다.
    # version(파일 수정 시각)이 바뀌면 새로 읽는다.
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
        # '데이터 관리'는 설치·운영 담당자용이다. 도민 메뉴에는 두지 않고, 데이터가 아직 없을 때나
        # 주소 뒤에 ?admin=1을 붙였을 때만 보인다(한 번 보이면 이 세션 동안 유지).
        if not records or st.query_params.get('admin') in ('1', 'true'):
            st.session_state.admin = True
        pages = ['거래처 찾기', '최근 관심 업체'] + (['데이터 관리'] if st.session_state.get('admin') else [])
        page = st.radio('메뉴', pages, key='page', horizontal=True, label_visibility='collapsed')
    with status:
        dot = '#228738' if ai_ready else '#9e6a00'
        st.html(f'<div class="tis-status"><span class="count">업체 <b>{len(records):,}</b>곳</span>'
                f'<span class="tis-dot" style="background:{dot}"></span>AI {"켜짐" if ai_ready else "한도 도달" if ai_limit_reached else "꺼짐"}</div>')
if st.session_state.flash:
    st.toast(st.session_state.flash, icon=':material/check_circle:')
    st.session_state.flash = ''
if any(c.is_demo for c in records):
    st.warning('가상 업체로 기능을 체험하는 중이에요. 실제 업체가 아닙니다.')


def go(step: int) -> None:
    st.session_state.step = step
    st.rerun()


notice: DeltaGenerator  # nav()가 매번 버튼 바 바로 위에 새로 만드는 알림 자리


def nav(back: int | None, next_label: str | None, key: str, status: str = '') -> bool:
    """화면 아래에 붙는 이전/다음 버튼 바. 이전은 바로 이동하고, 다음은 눌렸는지만 돌려준다(검증은 호출한 단계에서).

    버튼을 누른 뒤의 오류·진행 표시는 `notice` 자리(버튼 바 바로 위)에 그린다. 그냥 그리면 화면 아래에 붙은 바 밑으로 숨는다.
    """
    global notice
    notice = st.empty()
    with st.container(key=f'navbar_{key}'):
        left, right = st.columns([1, 1], vertical_alignment='center')
        with left, st.container(horizontal=True, vertical_alignment='center'):
            if back is not None and st.button('이전', key=f'{key}_back', icon=':material/arrow_back:'):
                go(back)
            if status:
                st.html(f'<span class="tis-pill">{escape(status)}</span>')
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


def form_section(key: str, title: str, note: str = '') -> DeltaGenerator:
    """상자 없는 구획: 왼쪽에 제목·설명, 오른쪽에 입력. 구획 사이는 가는 선 한 줄(설정 화면 방식).

    좁은 화면에서는 Streamlit이 두 열을 위아래로 쌓아 제목이 입력 위로 온다. 오른쪽 열을 돌려준다.
    """
    with st.container(key=key):
        left, right = st.columns([1, 3], gap='large')
        left.html(f'<p class="tis-sec-title">{escape(title)}</p>' + (f'<p class="tis-sec-note">{escape(note)}</p>' if note else ''))
    return right


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


def won(value: Decimal | None, currency: str = 'KRW', signed: bool = False) -> str:
    """화면용 금액: 800000.00 → 800,000원. 소수점이 있으면 둘째 자리까지. 계산·CSV에는 원래 값을 쓴다."""
    if value is None:
        return '미확정'
    sign = '+' if signed and value > 0 else ''
    number = f'{int(value):,}' if value == value.to_integral_value() else f'{value:,.2f}'
    return sign + number + ('원' if currency == 'KRW' else f' {currency}')


MONEY_DECIMAL = re.compile(r'(?<![\d.-])(-?\d+)\.(\d{2})(?!\d)')
BIG_NUMBER = re.compile(r'(?<![\d.,-])(-?\d{5,})(?![\d.,-])')


def pretty_numbers(text: str) -> str:
    """AI 문장의 금액만 읽기 쉽게: 765000.00 → 765,000, 35000 → 35,000. 날짜(2026-11-17)는 건드리지 않는다.

    AI에는 비교표 원래 값을 보내야 숫자 검증이 되므로, 형식은 화면에 그릴 때만 바꾼다.
    """
    text = MONEY_DECIMAL.sub(lambda m: f'{int(m[1]):,}' + ('' if m[2] == '00' else '.' + m[2]), text)
    return BIG_NUMBER.sub(lambda m: f'{int(m[1]):,}', text)


def source_line(companies: list[Company]) -> str:
    """후보 목록 위에 한 번만 보여 줄 출처 문장. 출처가 여럿이면 각 업체 줄에 따로 쓴다."""
    sources = {(c.source_name, str(c.source_date)) for c in companies}
    if len(sources) != 1:
        return ''
    name, day = sources.pop()
    return f'출처: {name} · 데이터 기준일 {day} · 생산품·주소는 과거 기록이라 현재 공급 여부와 연락처는 업체에 확인하세요.'


def show_company(c: Company, prefix: str, note: str = '', show_source: bool = True) -> None:
    """업체 한 곳을 상자 없이 목록의 한 줄로 그린다. 줄과 줄 사이는 얇은 구분선으로 나눈다.

    show_source=False: 목록 위에 출처를 한 번만 적은 경우(같은 문장을 업체마다 반복하지 않는다).
    """
    with st.container(key=f'card_{prefix}_{c.id}'):
        st.html(f'<div class="tis-row-head"><strong>{escape(c.name)}</strong>'
                f'<span>{escape(c.industry)} · {escape(c.region)}</span></div>'
                + (f'<p class="tis-row-note">{escape(note)}</p>' if note else ''))
        st.text('생산품 기록: ' + c.products)
        if show_source:
            st.caption(f'출처: {c.source_name} · 데이터 기준일 {c.source_date} · 생산품·주소는 과거 기록이라 현재 공급 여부와 연락처는 업체에 확인하세요.')
        chosen = c.id in st.session_state.shortlist
        with st.container(horizontal=True):
            # 상세에 보여 줄 것(웹사이트·사업자번호)이 있을 때만 버튼을 둔다. 상가 데이터에는 둘 다 없다.
            if (c.website or c.business_number) and st.button('상세 확인', key=f'{prefix}_view_{c.id}'):
                record_event(config.database_path, c.id, st.session_state.session_id, 'view')
                st.session_state['detail'] = c.id
            # 담기·빼기는 서로 다른 버튼(키)이다. 같은 키로 번갈아 쓰면 빠른 두 번 클릭이 '담고 바로 빼기'가 된다.
            if chosen:
                if st.button('✓ 담음 · 빼기', key=f'{prefix}_drop_{c.id}', help='누르면 비교 후보에서 뺍니다.'):
                    st.session_state.shortlist.remove(c.id)
                    st.rerun()
            elif st.button('비교에 담기', key=f'{prefix}_add_{c.id}', type='primary'):
                if len(st.session_state.shortlist) >= 5:
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
                    st.caption('국세청 확인 시각: ' + str(status['checked_at'])[:16].replace('T', ' '))
                if status.get('error'):
                    st.warning(status['error'])
            else:
                st.caption('국세청 상태: 아직 조회하지 않음')
            st.caption('사업자 상태는 품질·신용·납품 능력의 보증이 아닙니다.')


def run_search(on_step=None) -> None:
    """on_step: AI Agent가 도구를 쓸 때마다 단계 문장을 받는다(화면 실시간 표시)."""
    need, scope = st.session_state.need, st.session_state.scope
    region = scope['region'] if scope['region'] != '전체' else ('' if scope['city'] == '전체' else scope['city'])
    # AI 확인 질문에 답했으면 그 답을 붙여 다시 찾는다. 질문 속 예시('예: 간판, 포스기…')는 검색어를 흐리므로 빼고,
    # AI에는 '질문 → 답' 짝을, 키워드 검색에는 답만 붙인다.
    pairs = need.get('answers') or []
    use_agent = scope['use_ai'] and ai_ready
    if pairs and use_agent:
        query = need['query'] + ' / 사용자가 답한 추가 정보: ' + '; '.join(f'{q} → {a}' for q, a in pairs)
    else:
        query = ' '.join([need['query'], *(a for _, a in pairs)])
    request = SearchRequest(query=query[:2000], region=region, industry='' if scope['industry'] == '전체' else scope['industry'])
    state = st.session_state
    state.hits, state.questions, state.trace, state.summary, state.search_note = [], [], [], '', ''
    encoder = encoder_at('models/e5') if scope['semantic'] else None
    if scope['use_ai'] and ai_ready:
        try:
            count_ai()
            result = run_agent(config, records, request, encoder, on_step=on_step)
            state.hits, state.questions, state.trace, state.summary = result.hits, result.questions, result.trace, result.summary
        except AgentError as error:
            # AI가 실패해도 도민이 멈추지 않도록 키워드 검색 결과로 이어간다.
            state.search_note = f'{error} 키워드 검색 결과를 대신 보여줍니다.'
            state.hits = search(records, request, encoder)
    else:
        state.hits = search(records, request, encoder)
    state.searched = True
    # 보고서에 남길 검색 기록: 요청·조건·방식·Agent 단계(사람이 읽는 문장). 재현 확인용이며 원문 프롬프트는 남기지 않는다.
    used_ai = bool(state.trace)
    state.search_log = {
        'request': request.query, 'region': request.region or '제주 전체', 'industry': request.industry or '전체',
        'method': f'AI Agent ({config.provider} / {config.model})' if used_ai else '키워드 검색' + (' (AI 실패 후 대체)' if state.search_note else ''),
        'steps': trace_lines(state.trace), 'summary': state.summary,
        'found': [hit.company.name for hit in state.hits],
        'searched_at': datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M (한국 시간)'),
    }


def short_question(question: str) -> str:
    """AI 질문에서 예시 목록('예: 간판, 포스기…')을 떼어 낸 짧은 질문. 예시 낱말이 검색어로 섞이지 않게 한다."""
    return re.split(r'\s*\(?예[:)]', question)[0].strip().rstrip('?.').strip() or question


def search_now(slot: DeltaGenerator) -> None:
    """지금 조건으로 찾는다. AI Agent면 도구를 쓸 때마다 한 줄씩 slot에 보여 준다(5~15초 동안 무엇을 하는지 보이게)."""
    if st.session_state.scope['use_ai'] and ai_ready:
        with slot.container(), st.status('AI Agent가 데이터를 확인하며 찾는 중', expanded=True) as progress:
            run_search(on_step=lambda line: progress.write('✓ ' + line))
            progress.update(label='찾기 완료', state='complete')
    else:
        with slot, st.spinner('근거를 확인하며 찾는 중'):
            run_search()


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
        st.info('검색할 업체 데이터가 아직 없습니다. 위쪽 메뉴의 "데이터 관리"에서 CSV를 가져오거나, '
                '설치 폴더의 import_data.bat을 실행한 뒤 앱을 새로 고치세요.')
    if nav(None, '다음: 지역 고르기', 'n1'):
        if not query.strip():
            notice.error('필요한 품목이나 서비스를 적어 주세요.')
        elif journey == JOURNEYS[1] and not existing.strip():
            notice.error('비교할 기존 거래처 이름을 적어 주세요.')
        else:
            st.session_state.need = {'journey': journey, 'query': query.strip(), 'existing': existing.strip(), 'answers': []}
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
    if ai_limit_reached:
        st.caption(f'AI를 {config.ai_session_limit}번 써서 더는 쓸 수 없어요. 지금은 키워드로 찾습니다.')
    elif not ai_ready:
        st.caption('지금은 AI 없이 키워드로 찾습니다.')
    with st.expander('업종을 알고 있다면 (선택)'):
        industries = ['전체'] + sorted({c.industry for c in records})
        industry = st.selectbox('업종', industries, key='w_industry',
                                index=industries.index(scope['industry']) if scope['industry'] in industries else 0)
        # 로컬 의미 검색(선택 설치 모델)은 화면에서 고르지 않는다. 모델을 설치한 운영자만 코드에서 켤 수 있다.
        semantic = scope['semantic']
    if nav(1, '후보 찾기', 'n2'):
        st.session_state.scope = {'city': city, 'region': region, 'industry': industry, 'use_ai': use_ai, 'semantic': semantic}
        try:
            search_now(notice)
            go(3)
        except (ValueError, OSError):
            notice.error('검색 조건 또는 로컬 모델을 확인하세요. 의미 검색을 끄고 다시 시도할 수 있습니다.')


def step_candidates() -> None:
    state = st.session_state
    scope = state.scope
    place = scope['region'] if scope['region'] != '전체' else scope['city']
    st.subheader('비교할 후보를 고르세요')
    st.caption(f"'{state.need['query']}' · 지역 {place} · 최대 5곳까지 담을 수 있습니다."
               + (' · 추가 정보: ' + ', '.join(a for _, a in state.need['answers']) if state.need.get('answers') else ''))
    if state.search_note:
        st.warning(state.search_note)
    if state.summary or state.trace:
        with st.container(key='ai_summary'):
            ai_label('Agent 탐색 요약')
            if state.summary:
                st.text(state.summary)
            # Agent가 실제로 한 일(도구 호출)을 화살표로 이은 단계로 보여 준다. 원본 호출 기록(JSON)은 도민에게 보이지 않는다.
            steps = ''.join(f'<li>{escape(line)}</li>' for line in trace_lines(state.trace))
            if steps:
                st.html(f'<ol class="tis-trace" aria-label="Agent가 수행한 단계">{steps}</ol>')
            st.caption('요약 속 숫자는 데이터에서 직접 센 값만 씁니다. 실제 공급 여부는 업체에 확인하세요.')
    if state.questions:
        # AI가 요청이 모호하다고 본 점. 답하면 답을 붙여 다시 찾는다(한 번 묻고 끝나는 게 아니라 대화로 이어진다).
        with st.form('answers_form', border=False):
            body = form_section('sec_answers', 'AI가 더 묻는 것', '답하면 그 내용을 넣어 다시 찾아요. 모르는 질문은 비워 두세요.')
            answers = [body.text_input(question, key=f'w_answer_{number}') for number, question in enumerate(state.questions)]
            again = body.form_submit_button('답을 넣어 다시 찾기', key='reask', icon=':material/refresh:')
        if again:
            given = [[short_question(question), answer.strip()[:200]] for question, answer in zip(state.questions, answers) if answer.strip()]
            if not given:
                st.error('답을 하나 이상 적어 주세요.')
            else:
                state.need = {**state.need, 'answers': [*(state.need.get('answers') or []), *given][-6:]}
                try:
                    search_now(st.empty())
                    st.rerun()
                except (ValueError, OSError):
                    st.error('다시 찾지 못했습니다. 조건을 확인하세요.')
    if state.searched and not state.hits:
        st.info('아직 후보가 없습니다. 위 AI 질문에 답하면 그 내용을 넣어 다시 찾아요.' if state.questions else
                '조건에 맞는 근거를 찾지 못했습니다. 이전 단계에서 지역을 넓히거나, 첫 단계에서 품목을 짧게 적어 보세요.')
    shown = [by_id[hit.company.id] for hit in state.hits if hit.company.id in by_id]
    common = source_line(shown)
    if common:
        st.html(f'<p class="tis-source">{escape(common)}</p>')
    for hit in state.hits:
        if hit.company.id in by_id:
            show_company(by_id[hit.company.id], 'search', '일치 근거: ' + ' · '.join(r.replace('에서 일치: ', ' ') for r in hit.reasons),
                         show_source=not common)
    if nav(2, '다음: 문의 준비', 'n3', status=f'담은 후보 {len(state.shortlist)}/5'):
        if not state.shortlist:
            notice.error('비교할 후보를 1곳 이상 담아 주세요.')
        else:
            go(4)


def step_inquiry() -> None:
    state = st.session_state
    cond = state.conditions
    targets = flow_targets()
    st.subheader('견적 요청 조건을 한 번만 적으세요')
    st.caption('초안은 자동으로 보내지 않습니다. 내려받거나 복사해 직접 보내세요. '
               '초안 끝의 회신 양식을 업체가 채워 보내면, 5단계에 붙여 넣기만 해도 견적 칸이 채워져요.')
    st.caption('문의 대상: ' + ', '.join(name for _, name, _ in targets))
    with st.form('conditions_form', border=False):
        body = form_section('sec_c1', '보낼 조건', '업체마다 같은 조건으로 묻고, 5단계 견적 칸에도 그대로 채웁니다.')
        item = body.text_input('품목 (업체에 보낼 짧은 이름)', value=cond.get('item', ''), key='w_item',
                               placeholder=f"예: LED 간판 · 처음 적은 내용: {state.need['query']}")
        left, middle, right = body.columns(3)
        spec = left.text_input('규격', value=cond.get('specification', ''), key='w_spec', placeholder='예: 1200x600 LED')
        quantity = middle.text_input('수량', value=cond.get('quantity', ''), key='w_quantity', placeholder='예: 500')
        unit = right.text_input('단위', value=cond.get('unit', '개'), key='w_unit')
        notes = body.text_area('추가 요청 (희망 납기, 설치·배송 여부 등)', value=cond.get('notes', ''), key='w_notes')
        body = form_section('sec_c2', 'AI 확인 질문', '업체의 등록 업종에 맞춰 꼭 물어볼 점을 덧붙여요.')
        use_ai = body.checkbox('AI가 업체의 등록 업종·생산품을 보고 확인 질문을 덧붙이기', value=ai_ready, disabled=not ai_ready, key='w_inquiry_ai')
        create = body.form_submit_button('조건 저장하고 문의 초안 만들기', type='primary', key='create_inquiry')
    if create:
        try:
            if Decimal(quantity) <= 0 or not Decimal(quantity).is_finite():
                raise ValueError()
            drafts, note = {}, ''
            for key, name, company in targets:
                questions: list[str] = []
                if use_ai:
                    try:
                        if st.session_state.ai_used >= config.ai_session_limit:
                            raise AgentError('이 세션의 AI 사용 한도에 닿았습니다.')
                        count_ai()
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
                # 오른쪽 위 복사 버튼으로 문자·메일에 바로 붙여 넣는다.
                st.code(text, language=None, wrap_lines=True)
                st.download_button('이 초안 다운로드', text, f'거래잇수다_문의_{names[key]}.txt', 'text/plain', key=f'download_inquiry_{key}')
        st.download_button('초안 모두 한 파일로 받기', '\n\n----------\n\n'.join(drafts.values()), '거래잇수다_문의_전체.txt',
                           'text/plain', key='download_inquiry_all')
    if nav(3, '다음: 받은 견적 입력', 'n4'):
        if not state.conditions:
            notice.error('요청 조건을 먼저 저장하세요. 다음 단계 견적 입력에 같은 조건을 채웁니다.')
        else:
            go(5)


# 비교에 필요한데 AI 추출에서 비기 쉬운 칸. 비어 있으면 5단계에서 주황으로 표시한다.
CHECK_FIELDS = [('unit_price', '단가'), ('tax_included', '부가세 포함 여부'), ('shipping', '배송비'), ('extra_cost', '추가 비용'),
                ('minimum_order', '최소 주문 수량'), ('lead_days', '납기'), ('valid_until', '유효기간')]


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
    if extracted:
        # AI가 채운 칸 수와, 비교에 중요한데 비어 있는 칸을 알려 주고 그 칸을 주황으로 표시한다.
        blanks = [(name, label) for name, label in CHECK_FIELDS if extracted.get(name) is None]
        filled = sum(1 for name in extracted if name != 'company_name')
        with st.container(key='ai_extract_note'):
            if state.extracted.get('source') == 'form':
                st.html(f'<p class="tis-ai-label">업체 회신 양식에서 {filled}칸을 채웠어요</p>')
            else:
                ai_label(f'견적서에서 {filled}칸을 채웠어요')
            where = '회신' if state.extracted.get('source') == 'form' else '견적서'
            st.caption('원문과 대조해 고친 뒤 저장하세요.'
                       + (f' 주황색 칸은 {where}에서 찾지 못한 값입니다: ' + ', '.join(label for _, label in blanks) if blanks else ''))
        css = ''.join(f'.st-key-{prefix}_{"tax" if name == "tax_included" else name} :is(input, [data-baseweb="select"] > div)'
                      '{background:#fff8f2 !important; box-shadow: inset 0 0 0 1px #b34f00;}' for name, _ in blanks)
        if css:
            st.html(f'<style>{css}</style>')

    def field(container, label: str, name: str, default: str = '', help: str | None = None):
        value = seed.get(name)
        return container.text_input(label, value=str(default if value is None else value), key=f'{prefix}_{name}', help=help)

    # KRDS 신청서 작성 패턴: 필수 칸은 숨기지 않고 섹션 제목을 두며, 도움말은 화면 위가 아니라 입력 칸 옆(툴팁)에 둔다.
    with st.form(f'quote_form_{target}', border=False):
        body = form_section(f'sec_q1_{prefix}', '요청 조건', '4단계에서 적은 조건을 채웠어요. 견적서와 다르면 고쳐 주세요.')
        company_name = field(body, '업체명', 'company_name', name) if target == OTHER else name
        a, b, c, d = body.columns([2, 2, 1, 1])
        item = field(a, '품목', 'item')
        specification = field(b, '규격', 'specification', help='크기·재질·색 등 업체가 견적에 적은 사양')
        quantity = field(c, '수량', 'quantity')
        unit = field(d, '단위', 'unit', help='개, 박스, 장, m² 처럼 수량을 세는 단위')
        body = form_section(f'sec_q2_{prefix}', '금액', '모르는 금액은 빈칸으로 두세요. 0은 무료로 확인된 경우에만 넣어요.')
        a, b, c = body.columns(3)
        unit_price = field(a, '단가', 'unit_price', help='단위 1개당 가격. 견적서의 숫자만 넣어요(쉼표 없이).')
        tax_options = ['미확인', '포함', '별도']
        tax = b.selectbox('단가에 부가세 포함?', tax_options, key=f'{prefix}_tax',
                          index=tax_options.index({None: '미확인', True: '포함', False: '별도'}[seed.get('tax_included')]),
                          help='견적서에 "부가세 포함"이면 포함, "부가세 별도"이면 별도를 고르세요.')
        tax_rate = c.text_input('별도 세율 (%)', key=f'{prefix}_rate', help='부가세 별도일 때만 넣어요. 보통 10',
                                value=str(Decimal(str(seed['tax_rate'])) * 100) if seed.get('tax_rate') is not None else '')
        a, b, c = body.columns(3)
        shipping = field(a, '배송비 (세금 포함)', 'shipping', help='세금까지 더한 최종 배송비. 무료로 확인됐으면 0, 모르면 빈칸')
        extra_cost = field(b, '추가 비용 (세금 포함)', 'extra_cost', help='설치비·디자인비 등 단가 밖의 비용 합계. 없으면 0, 모르면 빈칸')
        currency = field(c, '통화', 'currency', 'KRW', help='원화는 KRW')
        body = form_section(f'sec_q3_{prefix}', '거래 조건과 근거', '납기·유효기간을 알면 비교표에 함께 표시돼요.')
        a, b = body.columns(2)
        minimum_order = field(a, '최소 주문 수량', 'minimum_order', help='업체가 받는 가장 적은 주문량. 요청 수량보다 크면 비교표에 표시돼요.')
        lead_days = field(b, '납기 (일)', 'lead_days', help='주문 후 받기까지 걸리는 날 수')
        a, b = body.columns(2)
        issued_at = field(a, '견적 발행일 (YYYY-MM-DD)', 'issued_at')
        valid_until = field(b, '유효기간 (YYYY-MM-DD)', 'valid_until', help='이 날짜가 지나면 견적 가격이 바뀔 수 있어요.')
        source_name = field(body, '견적 근거 (견적서 파일명·담당자 회신일 등)', 'source_name', '사용자 입력',
                            help='나중에 다시 확인할 수 있게 견적을 받은 경로를 적어요.')
        body = form_section(f'sec_q4_{prefix}', '확인하고 저장', '저장한 견적만 6단계 비교에 들어가요.')
        confirmed = body.checkbox('견적서 원문과 대조해 입력값을 확인했습니다', value=bool(seed.get('confirmed', False)), key=f'{prefix}_confirmed')
        save = body.form_submit_button('이 업체 견적 저장', type='primary', key='save_quote')
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
    # 회신 양식의 '문의 업체'로 업체를 찾았으면 그 업체를 골라 둔다(라디오를 그리기 전에만 바꿀 수 있다).
    pending = state.pop('pending_target', None)
    if pending in labels.values():
        st.session_state.w_quote_target = next(label for label, key in labels.items() if key == pending)
    chosen = st.radio('견적 업체', list(labels), horizontal=True, key='w_quote_target')
    target = labels.get(chosen or '', next(iter(labels.values())))
    # 업체마다 저장했는지 한눈에 보이게 한다(선택지 이름은 바꾸지 않는다: 이름이 바뀌면 선택이 풀린다).
    chips = ''.join(f'<li class="{"ok" if key in state.flow_quotes else ""}">{escape(name)} · '
                    f'{"저장함" if key in state.flow_quotes else "아직 입력 전"}</li>' for key, name in names.items())
    st.html(f'<ul class="tis-saved" aria-label="업체별 견적 저장 상태">{chips}</ul>')
    if target == EXISTING:
        st.caption('기존 거래처 견적은 6단계에서 비교 기준이 됩니다.')
    nts_ready = bool(config.nts_key and config.allow_external_data)
    with st.expander('사업자 상태 확인 (선택) · 국세청'):
        st.caption('사업자번호를 알면 국세청에서 계속·휴업·폐업 여부를 확인해 6단계 비교에 함께 보여 줘요. '
                   '상태가 품질·납품 능력을 보증하지는 않습니다.' + ('' if nts_ready else ' 국세청 API 키가 없어 지금은 쓸 수 없습니다.'))
        with st.form(f'nts_form_{target}', border=False):
            number = st.text_input('사업자번호', key=f'nts_no_{target}', placeholder='123-45-67890')
            check = st.form_submit_button('국세청 상태 확인', key=f'nts_check_{target}', disabled=not nts_ready)
        if check:
            try:
                with st.spinner('국세청에 확인하는 중'):
                    state.nts[target] = lookup_status(number, config)
            except ValueError as error:
                st.error(str(error))
        if target in state.nts:
            found = state.nts[target]
            closed = f" · 폐업일 {found['end_dt']}" if found.get('end_dt') else ''
            st.text(f"{found['b_no'][:3]}-{found['b_no'][3:5]}-{found['b_no'][5:]} → {found['label']}{closed}")
    # 견적서가 있으면 붙여넣기가 가장 빠르다: 아직 저장·추출하지 않은 업체에서는 펼쳐 둔다.
    first_time = ai_ready and target not in state.flow_quotes and state.extracted.get('target') != target
    with st.expander('받은 회신·견적서를 붙여 넣으면 칸을 채워요', expanded=first_time):
        st.caption('업체가 4단계 초안의 회신 양식을 채워 보냈다면 AI 없이 바로 채우고 업체도 골라 줘요. '
                   '양식이 아닌 견적서는 AI가 읽어요(내용이 OpenAI로 보내지니 연락처·개인정보는 지우세요). 채운 값은 원문과 대조하세요.')
        with st.form('extract_form', border=False):
            upload = st.file_uploader('회신·견적 파일 (선택)', type=['txt', 'pdf'], key='quote_file')
            text = st.text_area('또는 회신·견적 내용 붙여넣기', key='quote_text', max_chars=20000)
            extract = st.form_submit_button('칸 채우기', key='extract_submit')
        if extract:
            try:
                raw = quote_text(upload.getvalue(), upload.name) if upload else text
                reply = parse_reply(raw)
                if reply is not None:
                    # 회신 양식: 코드가 읽는다(AI·비용 없음). '문의 업체' 이름으로 견적 업체를 고른다.
                    found = next((key for key, name in names.items() if reply.company_name and name == reply.company_name), target)
                    values = reply.model_dump(mode='json', exclude_none=True)
                    state.extracted = {'target': found, 'values': values, 'source': 'form'}
                    state.pending_target = found
                    state.flash = f"{names.get(found, '이 업체')} 회신 양식에서 {sum(1 for k in values if k != 'company_name')}칸을 채웠습니다. 원문과 대조하세요."
                elif not ai_ready:
                    raise AgentError('회신 양식이 아닌 견적서는 AI가 읽어야 하는데, 지금은 AI를 쓸 수 없어요. 칸에 직접 입력하세요.')
                else:
                    count_ai()
                    with st.spinner('견적 추출 중'):
                        draft = extract_quote(config, raw)
                    state.extracted = {'target': target, 'values': draft.model_dump(mode='json', exclude_none=True), 'source': 'ai'}
                    state.flash = '추출값을 채웠습니다. 원문과 대조하고 빠진 조건을 입력하세요.'
                state.extraction_version += 1
                st.rerun()
            except AgentError as error:
                st.error(str(error))
    quote_form(target, names.get(target, ''), saved_by_id)
    if target in state.flow_quotes and st.button('이 업체 견적 삭제', key='delete_quote'):
        store.delete_quote(config.database_path, state.flow_quotes.pop(target))
        state.flash = '견적을 삭제했습니다.'
        st.rerun()
    if nav(4, '다음: 비교 결과 보기', 'n5', status=f'저장한 견적 {len(state.flow_quotes)}곳'):
        if not state.flow_quotes:
            notice.error('견적을 1개 이상 저장하세요.')
        else:
            go(6)


def display_table(rows: list[Comparison]) -> list[dict]:
    """화면의 자세한 비교표: 금액은 800,000원처럼, 비어 있는 열은 빼고 보여 준다(다운로드 CSV는 원래 값)."""
    table = [{'업체': r.quote.company_name, '품목': r.quote.item, '규격': r.quote.specification,
              '수량': f'{r.quote.quantity:,} {r.quote.unit}', '총액': won(r.total, r.quote.currency),
              '기준 대비 차액': won(r.difference, r.quote.currency, signed=True) if r.difference is not None else '비교 불가',
              '비교 제한': '; '.join(r.issues), '아직 모르는 것': '; '.join(r.warnings)} for r in rows]
    empty = [key for key in ('비교 제한', '아직 모르는 것') if not any(row[key] for row in table)]
    return [{k: v for k, v in row.items() if k not in empty} for row in table]


def result_cards(rows: list[Comparison], baseline_id: str, statuses: dict[str, dict] | None = None) -> None:
    """6단계 결론: 한 줄 요약 + 업체별 총액 카드(기준·더 싼 곳·비싼 곳·계산 불가 배지, 아직 모르는 것)."""
    base = next(r for r in rows if r.quote.id == baseline_id)
    cheaper = [r for r in rows if r.difference is not None and r.difference < 0]
    if cheaper and base.total:
        best = min(cheaper, key=lambda r: r.total or 0)
        assert best.difference is not None
        verdict = (f'같은 조건에서 가장 싼 곳은 <b>{escape(best.quote.company_name)}</b>입니다. '
                   f'기준({escape(base.quote.company_name)})보다 <b>{won(-best.difference, best.quote.currency)}</b> 저렴합니다.')
    elif any(r.difference is not None for r in rows if r is not base):
        verdict = f'같은 조건으로 비교한 후보 중 기준({escape(base.quote.company_name)})보다 싼 곳은 없습니다.'
    elif len(rows) == 1:
        verdict = '견적이 하나뿐입니다. 5단계에서 다른 업체 견적을 하나 더 저장하면 차액을 계산합니다.'
    else:
        verdict = '아직 같은 조건으로 금액을 비교할 수 있는 후보가 없습니다. 각 열의 사유를 확인하세요.'
    best_id = min(cheaper, key=lambda r: r.total or 0).quote.id if cheaper else None
    cards = []
    for r in [base] + [r for r in rows if r is not base]:
        currency = r.quote.currency
        if r is base:
            badge = '<span class="tis-badge base">비교 기준</span>'
        elif r.difference is not None and base.total:
            percent = abs(r.difference) / base.total * 100
            if r.difference < 0:
                badge = f'<span class="tis-badge cheaper">{won(-r.difference, currency)} ({percent:.1f}%) 저렴</span>'
            elif r.difference > 0:
                badge = f'<span class="tis-badge pricier">{won(r.difference, currency)} ({percent:.1f}%) 비쌈</span>'
            else:
                badge = '<span class="tis-badge base">기준과 같음</span>'
        else:
            badge = '<span class="tis-badge blocked">차액 계산 불가</span>'
        total = (f'<div class="total">{won(r.total, currency)}</div>' if r.total is not None
                 else '<div class="total unknown">총액 미확정</div>')
        notes = [escape(issue) for issue in r.issues] + [escape(w.replace(' 미확인', '')) + ' 확인' for w in r.warnings]
        listing = f'<ul>{"".join(f"<li>{n}</li>" for n in notes)}</ul>' if notes else ''
        status = (statuses or {}).get(r.quote.id)
        if status:
            listing += f'<p class="tis-nts">국세청: {escape(status["label"])} ({escape(status["checked_at"][:10])} 확인)</p>'
        kind = 'base' if r is base else 'best' if r.quote.id == best_id else ''
        cards.append(f'<div class="tis-card {kind}"><div class="name">{escape(r.quote.company_name)}</div>'
                     f'{total}{badge}{listing}</div>')
    st.html(f'<p class="tis-verdict">{verdict}</p><div class="tis-cards">{"".join(cards)}</div>')


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
        table = rows_for_export(rows)  # AI 해설·CSV에는 계산 원래 값을 쓴다.
        statuses = {qid: state.nts[key] for key, qid in state.flow_quotes.items() if key in state.nts}
        result_cards(rows, baseline_id, statuses)
        with st.expander('자세한 비교표 보기'):
            st.dataframe(display_table(rows), hide_index=True, alt='견적 총액과 비교 제한 조건')
            st.caption('차액 = 후보 총액 − 기준 총액. 조건이 다르거나 비용이 미확인인 견적은 차액 비교에서 제외합니다.')
        with st.container(horizontal=True):
            st.download_button('비교 보고서 (HTML)', html_report(rows, baseline_id, records, state.search_log or None,
                                                               store.import_history(config.database_path)),
                               '거래잇수다_비교.html', 'text/html', key='download_html')
            st.download_button('비교표 (CSV)', csv_report(rows), '거래잇수다_비교.csv', 'text/csv', key='download_csv')
        # 견적 내용이나 기준이 바뀌면 이전 해설을 보여주지 않는다.
        advice_key = repr((table, baseline_id))
        if st.button('AI 비교 해설 받기', key='explain_compare', disabled=not ai_ready):
            try:
                count_ai()
                with st.spinner('비교표를 해설하는 중'):
                    state.advice = (advice_key, explain_comparison(config, table, saved_by_id[baseline_id].company_name))
            except AgentError as error:
                st.error(str(error))
        if state.advice and state.advice[0] == advice_key:
            result = state.advice[1]
            with st.container(key='ai_advice'):
                ai_label('비교 해설')
                st.caption('해설 속 숫자는 위 비교표에 있는 값만 씁니다. 결정은 업체에 확인한 뒤 직접 하세요.')
                st.text(pretty_numbers(result.summary))
                if result.checks:
                    items = ''.join(f'<li>{escape(pretty_numbers(check))}</li>' for check in result.checks)
                    st.html(f'<p class="tis-ai-label">업체에 확인할 점</p><ul class="tis-checks">{items}</ul>')
                options = [(label, text) for label, text in [('지금 업체를 유지할 만한 경우', result.keep),
                                                             ('두 곳과 함께 거래할 만한 경우', result.parallel),
                                                             ('새 업체로 바꿀 만한 경우', result.switch)] if text]
                for column, (label, text) in zip(st.columns(len(options)) if options else [], options):
                    with column:
                        st.html(f'<div class="tis-ai-cols"><h5>{label}</h5></div>')
                        st.caption(pretty_numbers(text))
    nav(5, None, 'n6')
    if st.button('처음부터 새로 찾기', key='restart', icon=':material/restart_alt:'):
        for key, value in deepcopy(FLOW_DEFAULTS).items():
            st.session_state[key] = value
        go(1)


def page_popular() -> None:
    st.subheader('최근 30일, 많이 비교한 업체')
    st.caption('이 PC에서 비교 후보로 많이 담은 업체예요. 품질이나 신용 순위는 아닙니다.')
    prune_events(config.database_path)
    region = st.selectbox('관심 업체 지역', ['전체'] + sorted({c.region for c in records}), key='popular_region')
    allowed = {c.id for c in records if region == '전체' or c.region == region}
    rankings = popular(config.database_path, allowed_ids=allowed)
    if not rankings:
        st.info('아직 집계된 관심 기록이 없어요. 거래처 찾기에서 업체를 비교 후보로 담으면 여기에 모여요.')
    common = source_line([by_id[rank['company_id']] for rank in rankings])
    if common:
        st.html(f'<p class="tis-source">{escape(common)}</p>')
    for rank in rankings:
        c = by_id[rank['company_id']]
        if config.nts_key and config.allow_external_data and c.business_number:
            refresh_status(config.database_path, c, config)
        show_company(c, 'popular', f'관심 {rank["interest_count"]}회', show_source=not common)

def page_data() -> None:
    st.subheader('기업 데이터 가져오기')
    st.caption(f'AI 설정: {config.provider} / {config.model} · 이 세션 AI 사용 {st.session_state.ai_used}/{config.ai_session_limit}회'
               + ('' if ai_configured else ' · API 키 또는 외부 전송 허용이 없어 AI가 꺼져 있습니다')
               + ' · 이 PC 한 사람용입니다. 공용 PC에서는 사용 후 견적을 삭제하세요.')
    st.info('명세서가 아닌 실제 기업 행이 필요합니다. 원본 반출·가공·외부 전송 허용 여부는 각각 확인해야 합니다.')
    st.caption('필수 열: name/기업명, industry/업종명, products/주요생산품, region/주소_읍면동. 데이터 기준일은 source_date/데이터 기준일 또는 아래 공통 기준일로 입력합니다.')
    st.caption('제주데이터허브 「제주특별자치도 상가(상권) 정보」 CSV는 그대로 가져올 수 있습니다. 상호명·상권업종중분류명을 업체명·업종으로, '
               '상권업종소분류명·표준산업분류명을 생산품으로, 시군구명·행정동명을 지역으로 씁니다. 파일에 기준일이 없으니 공통 기준일(수집일)을 입력하세요.')
    with st.form('import_form', border=False):
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
