from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import streamlit as st
from pydantic import ValidationError

from trade_itsuda import store
from trade_itsuda.agent import AgentError, extract_quote, quote_text, run_agent
from trade_itsuda.business import refresh_status
from trade_itsuda.comparison import compare
from trade_itsuda.config import settings
from trade_itsuda.exporting import csv_report, html_report, inquiry, rows_for_export
from trade_itsuda.ingest import demo_companies, import_companies, parse_file
from trade_itsuda.models import Quote, SearchRequest
from trade_itsuda.popularity import popular, prune_events, record_event
from trade_itsuda.retrieval import load_encoder, search

st.set_page_config(page_title='거래잇수다', page_icon=':material/handshake:', layout='wide')
st.title('거래잇수다')
st.caption('제주 거래처를 찾고, 기존 업체와 같은 조건으로 비교하고, 견적 문의까지 준비하세요.')
try:
    config = settings()
    store.initialize(config.database_path)
except (ValueError, OSError):
    st.error('환경 설정 또는 데이터 폴더를 확인하세요. README의 설치 절차를 참고하세요.')
    st.stop()

for key, value in {'session_id': str(uuid4()), 'shortlist': [], 'hits': [], 'questions': [], 'trace': [],
                   'extracted': {}, 'extraction_version': 0, 'flash': ''}.items():
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
if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = ''
if any(c.is_demo for c in records):
    st.warning('가상 데이터로 기능을 체험 중입니다. 실제 기업 정보·대회 필수 데이터 활용 실적이 아닙니다.')
if not config.llm_key or not config.allow_external_data:
    st.info('현재 기본 검색·직접 견적 입력 모드입니다. AI 검색·추출에는 API 키와 외부 전송 허용 설정이 필요합니다.')
with st.sidebar:
    page = st.radio('메뉴', ['거래처 찾기', '견적 비교', '문의 준비', '최근 관심 업체', '데이터 관리'], key='page')
    st.caption(f'등록 기업 {len(records):,}곳 · 비교 선택 {len(st.session_state.shortlist)}곳')
    st.caption(f'LLM: {config.provider} / {config.model}')
    st.caption('국세청 키: ' + ('설정됨' if config.nts_key else '미설정'))
    st.caption('로컬 PC 단일 사용자용입니다. 공용 PC 사용 후 견적을 삭제하세요.')


def show_company(c, prefix):
    with st.container(border=True):
        st.subheader(c.name)
        st.text(f'{c.industry} · {c.region}')
        st.text('생산품 기록: ' + c.products)
        st.caption(f'출처: {c.source_name} · 데이터 기준일: {c.source_date}')
        st.caption('생산품·주소는 과거 기록입니다. 현재 공급 가능 여부와 연락처는 업체에 확인하세요.')
        with st.container(horizontal=True):
            if st.button('상세 확인', key=f'{prefix}_view_{c.id}'):
                record_event(config.database_path, c.id, st.session_state.session_id, 'view')
                st.session_state['detail'] = c.id
            if st.button('비교에 담기', key=f'{prefix}_add_{c.id}'):
                if c.id not in st.session_state.shortlist:
                    if len(st.session_state.shortlist) >= 5:
                        st.error('후보는 최대 5곳까지 선택할 수 있습니다.')
                    else:
                        st.session_state.shortlist.append(c.id)
                        record_event(config.database_path, c.id, st.session_state.session_id, 'compare')
                        st.session_state.flash = '비교에 담았습니다. 견적 비교 메뉴에서 견적을 입력하세요.'
                        st.rerun()
        if st.session_state.get('detail') == c.id:
            if c.website:
                st.link_button('등록된 웹사이트 열기', c.website)
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


if page == '거래처 찾기':
    st.subheader('어떤 거래처가 필요한가요?')
    journey = st.segmented_control('이용 목적', ['새 거래처 찾기', '기존 거래처와 비교'], default='새 거래처 찾기', key='journey')
    if journey == '기존 거래처와 비교':
        st.info('후보를 비교에 담은 뒤, 견적 비교에서 기존 업체를 직접 입력하고 기준 견적으로 선택하세요.')
    if not records:
        st.info('데이터 관리에서 승인된 기업 데이터를 가져오거나 가상 데모를 불러오세요.')
    with st.form('search_form'):
        query = st.text_input('필요한 품목이나 서비스', placeholder='예: 라벨 스티커, 종이 박스, 유리병', key='query', max_chars=2000)
        left, right = st.columns(2)
        with left:
            region = st.selectbox('지역', ['전체'] + sorted({c.region for c in records}), key='region')
        with right:
            industry = st.selectbox('업종', ['전체'] + sorted({c.industry for c in records}), key='industry')
        use_ai = st.checkbox('AI가 검색 도구를 호출해 후보를 골라주기', disabled=not (config.llm_key and config.allow_external_data), key='use_ai')
        semantic = st.checkbox('로컬 의미 검색 함께 사용', key='semantic', help='선택 설치 및 models/e5 모델 준비가 필요합니다. 자동 다운로드하지 않습니다.')
        submitted = st.form_submit_button('거래처 찾기', type='primary', key='search_submit')
    if submitted:
        st.session_state.hits, st.session_state.questions, st.session_state.trace = [], [], []
        try:
            request = SearchRequest(query=query, region='' if region == '전체' else region, industry='' if industry == '전체' else industry)
            with st.spinner('근거를 확인하며 검색 중'):
                encoder = encoder_at('models/e5') if semantic else None
                if use_ai:
                    result = run_agent(config, records, request, encoder)
                    st.session_state.hits, st.session_state.questions, st.session_state.trace = result.hits, result.questions, result.trace
                else:
                    st.session_state.hits = search(records, request, encoder)
            st.session_state['searched'] = True
        except AgentError as error:
            st.error(str(error))
        except (ValueError, OSError):
            st.error('검색 조건 또는 로컬 모델을 확인하세요. 품목을 입력하고 기본 검색부터 시도할 수 있습니다.')
    for question in st.session_state.questions:
        st.text('추가로 확인할 점: ' + question)
    if st.session_state.trace:
        with st.expander('Agent 수행 기록'):
            st.json(st.session_state.trace)
    if st.session_state.get('searched') and not st.session_state.hits:
        st.info('조건에 맞는 근거를 찾지 못했습니다. 품목을 짧게 입력하거나 지역·업종 조건을 넓혀보세요.')
    for hit in st.session_state.hits:
        if hit.company.id in by_id:
            st.caption(hit.method + ' · ' + ' / '.join(hit.reasons))
            show_company(by_id[hit.company.id], 'search')

elif page == '견적 비교':
    st.subheader('기존 업체와 후보의 견적을 같은 조건으로 비교하세요')
    st.caption('빈 금액은 미확인입니다. 무료로 확인된 항목만 0을 입력하세요. 배송비·추가 비용은 세금 포함 최종 금액입니다.')
    if st.session_state.shortlist:
        selected = st.multiselect('비교 후보 목록', st.session_state.shortlist, default=st.session_state.shortlist,
                                  format_func=lambda cid: by_id[cid].name, key='shortlist_editor')
        if st.button('후보 목록 적용', key='apply_shortlist'):
            st.session_state.shortlist = [cid for cid in selected if cid in by_id][:5]
            st.rerun()
    with st.expander('AI로 견적 텍스트·PDF에서 입력값 추출'):
        st.caption('연락처·개인정보를 제거하고 외부 전송 가능한 자료만 사용하세요. 추출값은 반드시 원문과 대조하세요.')
        with st.form('extract_form'):
            upload = st.file_uploader('견적 파일 (선택)', type=['txt', 'pdf'], key='quote_file')
            text = st.text_area('또는 견적 원문 붙여넣기', key='quote_text', max_chars=20000)
            extract = st.form_submit_button('AI 추출 후 입력 양식에 채우기', key='extract_submit', disabled=not (config.llm_key and config.allow_external_data))
        if extract:
            try:
                raw = quote_text(upload.getvalue(), upload.name) if upload else text
                with st.spinner('견적 추출 중'):
                    draft = extract_quote(config, raw)
                st.session_state.extracted = draft.model_dump(mode='json', exclude_none=True)
                st.session_state.extraction_version += 1
                st.session_state['edit_quote'] = 'new'
                st.session_state.flash = '추출값을 채웠습니다. 원문과 대조하고 빠진 조건을 입력하세요.'
                st.rerun()
            except AgentError as error:
                st.error(str(error))
    saved = store.quotes(config.database_path)
    saved_by_id = {q.id: q for q in saved}
    edit_id = st.selectbox('작성·수정할 견적', ['new'] + list(saved_by_id),
                           format_func=lambda qid: '새 견적' if qid == 'new' else saved_by_id[qid].company_name + ' / ' + saved_by_id[qid].item,
                           key='edit_quote')
    seed = saved_by_id[edit_id].model_dump(mode='json') if edit_id in saved_by_id else st.session_state.extracted
    prefix = f'q_{edit_id}_{st.session_state.extraction_version}'
    candidates = list(st.session_state.shortlist)
    seed_company = seed.get('company_id')
    if seed_company in by_id and seed_company not in candidates:
        candidates.append(seed_company)
    company_options = ['manual'] + candidates
    target = st.selectbox('견적 업체', company_options, index=company_options.index(seed_company) if seed_company in company_options else 0,
                          format_func=lambda cid: '기존 업체 등 직접 입력' if cid == 'manual' else by_id[cid].name, key=prefix + '_target')
    with st.form('quote_form'):
        def field(label, name, default=''):
            value = seed.get(name)
            return st.text_input(label, value=str(default if value is None else value), key=prefix + '_' + name)
        company_name = field('업체명 (직접 입력할 때)', 'company_name')
        item = field('품목', 'item')
        specification = field('규격 (예: 가로 50mm × 세로 50mm / 무광)', 'specification')
        quantity = field('수량', 'quantity')
        unit = field('단위 (예: 개)', 'unit')
        unit_price = field('단가 (미확인이면 빈칸)', 'unit_price')
        currency = field('통화 코드', 'currency', 'KRW')
        tax_options = ['미확인', '포함', '별도']
        tax_seed = {None: '미확인', True: '포함', False: '별도'}[seed.get('tax_included')]
        tax = st.selectbox('단가의 세금 포함 여부', tax_options, index=tax_options.index(tax_seed), key=prefix + '_tax')
        tax_rate = st.text_input('별도 세율 (%)', value=str(Decimal(str(seed['tax_rate'])) * 100) if seed.get('tax_rate') is not None else '', key=prefix + '_rate')
        shipping = field('배송비 (세금 포함, 무료이면 0)', 'shipping')
        extra_cost = field('추가 비용 (세금 포함, 없으면 0)', 'extra_cost')
        minimum_order = field('최소 주문 수량 (미확인이면 빈칸)', 'minimum_order')
        lead_days = field('납기 (일, 미확인이면 빈칸)', 'lead_days')
        issued_at = field('견적 발행일 (YYYY-MM-DD, 미확인이면 빈칸)', 'issued_at')
        valid_until = field('견적 유효기간 (YYYY-MM-DD, 미확인이면 빈칸)', 'valid_until')
        source_name = field('견적 근거 (예: 업체 견적서 파일명·담당자 회신일)', 'source_name', '사용자 입력')
        confirmed = st.checkbox('원문과 대조해 입력값을 확인했습니다', value=bool(seed.get('confirmed', False)), key=prefix + '_confirmed')
        save = st.form_submit_button('견적 저장', type='primary', key='save_quote')
    if save:
        try:
            if target not in company_options:
                raise ValueError()
            qid = edit_id if edit_id in saved_by_id else str(uuid4())
            quote = Quote(id=qid, company_id=target if target != 'manual' else 'manual-' + qid,
                          company_name=by_id[target].name if target in by_id else company_name, item=item, specification=specification,
                          unit=unit, quantity=quantity, unit_price=unit_price or None, currency=currency,
                          tax_included={'미확인': None, '포함': True, '별도': False}[tax],
                          tax_rate=Decimal(tax_rate) / 100 if tax_rate else None, shipping=shipping or None,
                          extra_cost=extra_cost or None, minimum_order=minimum_order or None, lead_days=lead_days or None,
                          issued_at=issued_at or None, valid_until=valid_until or None, source_name=source_name, confirmed=confirmed)
            store.save_quotes(config.database_path, [quote])
            st.session_state.flash = '견적을 저장했습니다. 아래에서 기준 견적을 선택하세요.'
            st.rerun()
        except (ValueError, ArithmeticError, KeyError):
            st.error('입력값을 확인하세요. 필수 항목·숫자·통화 코드·날짜 순서가 올바르지 않습니다.')
    if saved:
        st.divider()
        selected_ids = st.multiselect('비교할 견적 (최대 6개)', list(saved_by_id), default=list(saved_by_id)[:6],
                                      format_func=lambda qid: saved_by_id[qid].company_name + ' / ' + saved_by_id[qid].item, key='compare_ids')
        if selected_ids and len(selected_ids) <= 6 and all(qid in saved_by_id for qid in selected_ids):
            baseline_id = st.selectbox('기준 견적 (기존 거래 업체 등)', selected_ids,
                                       format_func=lambda qid: saved_by_id[qid].company_name, key='baseline_id')
            rows = compare([saved_by_id[qid] for qid in selected_ids], baseline_id)
            st.dataframe(rows_for_export(rows), hide_index=True, alt='견적 총액과 비교 제한 조건')
            st.caption('차액 = 후보 총액 − 기준 총액. 조건이 다르거나 비용이 미확인인 견적은 차액 비교에서 제외합니다.')
            with st.container(horizontal=True):
                st.download_button('비교 보고서 (HTML)', html_report(rows, baseline_id, records), '거래잇수다_비교.html', 'text/html', key='download_html')
                st.download_button('비교표 (CSV)', csv_report(rows), '거래잇수다_비교.csv', 'text/csv', key='download_csv')
        elif len(selected_ids) > 6:
            st.error('견적은 최대 6개를 선택하세요.')
        delete_id = st.selectbox('삭제할 견적', list(saved_by_id), format_func=lambda qid: saved_by_id[qid].company_name, key='delete_quote_id')
        if st.button('선택 견적 삭제', key='delete_quote') and delete_id in saved_by_id:
            store.delete_quote(config.database_path, delete_id)
            st.session_state.flash = '선택 견적을 삭제했습니다.'
            st.rerun()

elif page == '문의 준비':
    st.subheader('동일한 조건으로 견적을 요청하세요')
    st.caption('직접 발송할 수 있는 문의 초안을 만듭니다. 자동 발송하지 않습니다.')
    candidates = [by_id[cid].name for cid in st.session_state.shortlist]
    with st.form('inquiry_form'):
        name = st.text_input('문의할 업체명', value=candidates[0] if candidates else '', key='inquiry_company')
        item = st.text_input('요청 품목', key='inquiry_item')
        spec = st.text_input('요청 규격', key='inquiry_spec')
        quantity = st.text_input('요청 수량', key='inquiry_quantity')
        unit = st.text_input('요청 단위', key='inquiry_unit')
        notes = st.text_area('추가 요청', key='inquiry_notes')
        create = st.form_submit_button('문의 초안 만들기', key='create_inquiry')
    if create:
        try:
            if Decimal(quantity) <= 0 or not Decimal(quantity).is_finite():
                raise ValueError()
            st.session_state['inquiry_draft'] = inquiry(name, item, spec, quantity, unit, notes)
        except (ValueError, ArithmeticError):
            st.error('필수 항목과 양수 수량을 입력하세요.')
    if st.session_state.get('inquiry_draft'):
        st.text(st.session_state.inquiry_draft)
        st.download_button('문의 초안 다운로드', st.session_state.inquiry_draft, '거래잇수다_문의.txt', 'text/plain', key='download_inquiry')

elif page == '최근 관심 업체':
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
        if config.nts_key and config.allow_external_data:
            refresh_status(config.database_path, c, config)
        st.caption(f'관심 {rank["interest_count"]}회 · 상세 보기 {rank["views"]}회 · 비교 선택 {rank["comparisons"]}회')
        show_company(c, 'popular')
    st.caption('이 화면을 여는 동안 상위 5개 업체의 사업자 상태만 캐시 주기에 따라 갱신합니다. 앱이 꺼져 있을 때나 생산품 정보는 자동 갱신하지 않습니다.')

elif page == '데이터 관리':
    st.subheader('기업 데이터 가져오기')
    st.info('명세서가 아닌 실제 기업 행이 필요합니다. 원본 반출·가공·외부 전송 허용 여부는 각각 확인해야 합니다.')
    st.caption('필수 열: name/기업명, industry/업종명, products/주요생산품, region/주소_읍면동. 데이터 기준일은 source_date/데이터 기준일 또는 아래 공통 기준일로 입력합니다.')
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
