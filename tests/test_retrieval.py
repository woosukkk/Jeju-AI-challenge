import numpy as np

from trade_itsuda.ingest import demo_companies
from trade_itsuda.models import SearchRequest
from trade_itsuda.retrieval import search


def test_keyword_filter_and_no_invented_supplier():
    hits = search(demo_companies(), SearchRequest(query='라벨 스티커'))
    assert hits[0].company.id == 'demo-print'
    assert hits[0].reasons
    assert search(demo_companies(), SearchRequest(query='반도체')) == []
    assert search(demo_companies(), SearchRequest(query='라벨', region='서귀포')) == []


def test_sentence_queries_with_particles_and_compounds():
    expected = {
        '유리병을 구하고 싶어요': 'demo-glass',
        '박스가 필요해요': 'demo-box',
        '종이상자 주문': 'demo-box',
        '잼병이요': 'demo-glass',
        '스티커를 인쇄해 줄 곳': 'demo-print',
    }
    for query, company_id in expected.items():
        hits = search(demo_companies(), SearchRequest(query=query))
        assert hits and hits[0].company.id == company_id, query
    assert search(demo_companies(), SearchRequest(query='반도체가 필요해요')) == []


def test_takeout_food_is_not_a_packaging_supplier():
    from trade_itsuda.models import Company
    shops = [Company(id='food', name='가상분식', industry='기타 간이', products='김밥/만두/분식 / 간이 음식 포장 판매 전문점',
                     region='제주시 이도1동', source_name='테스트', source_date='2025-09-18'),
             Company(id='pack', name='가상포장', industry='기타 사업 서비스', products='포장/충전업 / 포장 및 충전업',
                     region='제주시 이도1동', source_name='테스트', source_date='2025-09-18')]
    hits = search(shops, SearchRequest(query='포장 박스가 필요해요'))
    assert [h.company.id for h in hits] == ['pack']
    assert hits[0].reasons[0] == '생산품에서 일치: 포장'


def test_name_only_matches_yield_to_product_matches():
    from trade_itsuda.models import Company
    def shop(cid, name, products):
        return Company(id=cid, name=name, industry='기타', products=products, region='제주시 연동',
                       source_name='테스트', source_date='2025-09-18')
    shops = [shop('salon', '중앙로박스', '미용실 / 두발 미용업'), shop('pack', '가상상회', '포장/충전업 / 포장 및 충전업')]
    assert [h.company.id for h in search(shops, SearchRequest(query='박스'))] == ['pack']
    # 업체명을 그대로 입력하면(기존 거래처 이름 검색) 그 업체가 맨 앞에 온다.
    assert search(shops, SearchRequest(query='중앙로박스'))[0].company.id == 'salon'


def test_industry_filter_accepts_sub_category_names():
    from trade_itsuda.models import Company
    sign = Company(id='sign', name='가상간판', industry='인쇄·제품제작', products='명함/간판/광고물 제작 / 간판 및 광고물 제조업',
                   region='제주시 연동', source_name='테스트', source_date='2025-09-18')
    assert search([sign], SearchRequest(query='간판', industry='명함/간판/광고물 제작'))[0].company.id == 'sign'
    assert search([sign], SearchRequest(query='간판', industry='한식')) == []


def test_semantic_is_filtered_and_labelled():
    class Encoder:
        def encode(self, texts, **kwargs):
            assert texts[0].startswith('query: ')
            return np.array([[1., 0.]] * len(texts))
    hits = search(demo_companies(), SearchRequest(query='반도체', region='서귀포'), Encoder())
    assert len(hits) == 2
    assert all(h.method == '키워드 + 의미' and '확인 필요' in h.reasons[0] for h in hits)


def test_real_data_failures_short_names_own_shop_words_and_broad_words():
    # 2026-11-17 실제 상가 데이터 측정에서 나온 오검색을 가상 업소로 재현한다.
    from trade_itsuda.models import Company
    def shop(cid, name, industry, products):
        return Company(id=cid, name=name, industry=industry, products=products, region='제주시 연동',
                       source_name='테스트', source_date='2025-09-18')
    shops = [shop('bag', '박스', '섬유·의복·신발 소매', '가방 소매업'),
             shop('pack', '가상상회', '기타 사업 서비스', '포장/충전업 / 포장 및 충전업'),
             shop('food', '가상식당', '한식', '백반/한정식 / 한식 일반 음식점업'),
             shop('canteen', '가상구내', '구내식당·뷔페', '구내식당 / 기관 구내식당업'),
             shop('fix', '가상수리', '가전제품 수리', '가전제품 수리업'),
             shop('rent', '가상렌탈', '운송장비 대여', '기타 운송장비 대여업')]
    # 두 글자 상호 '박스'는 업체명 입력이 아니라 흔한 낱말이다.
    assert [h.company.id for h in search(shops, SearchRequest(query='택배 박스 포장재'))] == ['pack']
    assert search(shops, SearchRequest(query='박스'))[0].company.id == 'bag'  # 질의 전체가 상호면 그 업소를 찾는다.
    # '식당'은 사용자 자신의 가게라서 음식점을 후보로 만들지 않는다.
    assert [h.company.id for h in search(shops, SearchRequest(query='식당 업소용 냉장고 수리'))] == ['fix']
    assert [h.company.id for h in search(shops, SearchRequest(query='식당'))] == ['canteen']  # 질의가 이 말뿐이면 그대로 찾는다.
    # 구체적인 품목이 데이터에 없으면 '장비'만으로 후보를 만들지 않는다. 품목이 있으면 넓은 말 일치도 쓴다.
    assert search(shops, SearchRequest(query='반도체 웨이퍼 장비')) == []
    assert [h.company.id for h in search(shops, SearchRequest(query='운송 장비'))] == ['rent']
