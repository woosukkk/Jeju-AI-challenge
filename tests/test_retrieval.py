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


def test_semantic_is_filtered_and_labelled():
    class Encoder:
        def encode(self, texts, **kwargs):
            assert texts[0].startswith('query: ')
            return np.array([[1., 0.]] * len(texts))
    hits = search(demo_companies(), SearchRequest(query='반도체', region='서귀포'), Encoder())
    assert len(hits) == 2
    assert all(h.method == '키워드 + 의미' and '확인 필요' in h.reasons[0] for h in hits)
