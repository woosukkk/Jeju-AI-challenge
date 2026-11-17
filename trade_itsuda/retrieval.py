import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import Company, SearchRequest


@dataclass(frozen=True)
class SearchHit:
    company: Company
    score: float
    reasons: list[str]
    method: str = '키워드'


def document(company: Company) -> str:
    return f'{company.name} / {company.industry} / {company.products} / {company.region}'


STOP_WORDS = {'업체', '거래처', '찾아줘', '찾고', '싶어', '필요해', '있는', '추천', '제주', '제주도',
              '필요', '있어', '구하고', '구해', '주문', '어디', '알려줘', '파는', '하는', '해주는'}
# 긴 어미부터 떼어 낸다. 명사 끝 글자와 겹칠 수 있어 원래 낱말도 함께 검색한다.
SUFFIXES = sorted({'을', '를', '이', '가', '은', '는', '도', '만', '에', '의', '와', '과', '랑', '요', '로',
                   '으로', '에서', '에게', '한테', '까지', '부터', '이랑', '이요', '이나', '나',
                   '해', '해요', '하고', '해줄', '할', '해서', '해줘'}, key=len, reverse=True)
CONCEPTS = {'포장': ['박스', '상자', '패키지'], '라벨': ['스티커'],
            '용기': ['유리병', '잼병'], '청소': ['시설 관리']}
# 품목 낱말이 다른 뜻으로 쓰인 분류명. 상가(상권) 정보의 '간이 음식 포장 판매 전문점'(포장 판매 음식점)이
# '포장' 공급처로 잡히지 않게 일치 판정 전에 지운다. 실제 오검색 사례가 생기면 보완한다.
NOISE_PHRASES = ('음식 포장 판매', '포장 판매')
# 사용자 자신의 가게를 가리키는 말. '식당 냉장고 수리'에서 식당은 찾는 공급처가 아니라 쓰는 곳이다.
# 이 말만으로 음식점이 후보가 되지 않게 검색어에서 뺀다(질의가 이 말뿐이면 그대로 둔다). 2026-11-17 실제 데이터 측정에서 발견.
CONTEXT_WORDS = {'가게', '매장', '식당', '업소', '업소용', '점포', '사무실', '우리'}
# 범위가 넓은 말. '반도체 웨이퍼 장비'처럼 구체적인 품목 낱말이 데이터에 전혀 없을 때 '장비'만으로 운송장비 대여점을
# 후보로 내지 않게 한다. 구체적인 낱말이 데이터 어딘가에 있으면(예: '건축 자재') 넓은 말 일치도 그대로 쓴다.
GENERIC_WORDS = {'장비', '제품', '용품', '자재', '재료', '기계', '물품', '상품', '서비스'}


def stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[:-len(suffix)]
    return word


def tokens(query: str) -> list[set[str]]:
    """질의 낱말마다 일치로 인정할 표현 묶음을 만든다. 묶음 하나는 점수에 한 번만 반영된다."""
    groups = []
    for word in dict.fromkeys(re.findall(r'[가-힣a-zA-Z0-9]{2,}', query.lower())):
        base = stem(word)
        if word in STOP_WORDS or base in STOP_WORDS:
            continue
        variants = {word, base}
        # shortcut: 작은 품목 사전만 확장, 실제 검색 실패 사례가 쌓이면 사전을 보완.
        for concept, synonyms in CONCEPTS.items():
            if concept in base or any(synonym in base for synonym in synonyms):
                variants.update([concept, *synonyms])
        groups.append(variants)
    focused = [group for group in groups if not group & CONTEXT_WORDS]
    return focused or groups


def matched_terms(groups: list[set[str]], text: str) -> list[str]:
    text = text.lower()
    for phrase in NOISE_PHRASES:
        text = text.replace(phrase, ' ')
    compact = re.sub(r'\s+', '', text)
    matched = set()
    for variants in groups:
        hit = sorted(v for v in variants if v in text or v.replace(' ', '') in compact)
        if hit:
            matched.add(max(hit, key=len))
    return sorted(matched)


def load_encoder(model_path: str):
    if not Path(model_path).is_dir():
        raise ValueError('로컬 임베딩 모델 폴더가 없습니다. 기본 키워드 검색을 사용하세요.')
    try:
        from sentence_transformers import SentenceTransformer  # ty: ignore[import-not-found]
    except ImportError:
        raise ValueError('의미 검색에는 requirements-semantic.txt 설치가 필요합니다.') from None
    return SentenceTransformer(model_path, device='cpu', local_files_only=True)


def search(records: list[Company], request: SearchRequest, encoder=None) -> list[SearchHit]:
    # 업종 조건은 중분류(업종)뿐 아니라 소분류·표준산업분류(생산품 칸)로 적어도 걸리게 한다.
    filtered = [c for c in records if (not request.region or request.region in c.region)
                and (not request.industry or request.industry in c.industry or request.industry in c.products)]
    if not filtered:
        return []
    terms = tokens(request.query)
    semantic = np.zeros(len(filtered))
    if encoder is not None:
        vectors = np.asarray(encoder.encode(
            ['query: ' + request.query] + ['passage: ' + document(c) for c in filtered],
            normalize_embeddings=True), dtype=float)
        if vectors.ndim != 2 or vectors.shape[0] != len(filtered) + 1 or not np.isfinite(vectors).all():
            raise ValueError('임베딩 결과를 검증할 수 없습니다.')
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.maximum(norms, 1e-12)
        semantic = vectors[1:] @ vectors[0]
    hits = []
    generic_only: set[int] = set()  # 넓은 말로만 일치한 후보 (hits의 위치)
    found: set[str] = set()  # 데이터 어딘가에서 일치한 낱말
    query_compact = re.sub(r'\s+', '', request.query.lower())
    for index, company in enumerate(filtered):
        evidence = []
        weight = 0
        matched_all: set[str] = set()
        for label, text, multiplier in [('생산품', company.products, 3), ('업종', company.industry, 2), ('업체명', company.name, 1)]:
            matched = matched_terms(terms, text)
            if matched:
                weight += multiplier * len(matched)
                matched_all.update(matched)
                evidence.append(f'{label}에서 일치: {", ".join(matched)}')
        if weight == 0 and encoder is None:
            continue
        if encoder is not None and weight == 0:
            evidence.append('의미 검색 탐색 후보: 실제 취급 품목은 업체 확인 필요')
        name = re.sub(r'\s+', '', company.name.lower())
        # 2~3글자 상호('박스', '청소')는 흔한 낱말과 겹친다. 질의 전체가 그 상호일 때만 업체명 입력으로 본다.
        typed_name = name in query_compact and (len(name) >= 4 or name == query_compact)
        # 상호에 품목 낱말만 들어간 업소(예: '○○박스' 미용실)는 취급 근거가 아니므로 뺀다.
        # 사용자가 업체명을 통째로 입력한 경우(기존 거래처 찾기)만 남기고 맨 앞에 둔다.
        if evidence and all(reason.startswith('업체명') for reason in evidence) and not typed_name:
            continue
        score = float(weight + semantic[index] + (10 if typed_name and evidence else 0))
        found.update(matched_all)
        if matched_all and matched_all <= GENERIC_WORDS and not typed_name:
            generic_only.add(len(hits))
        hits.append(SearchHit(company, score, evidence, '키워드 + 의미' if encoder else '키워드'))
    if any(not group & found and not group & GENERIC_WORDS for group in terms):
        hits = [hit for position, hit in enumerate(hits) if position not in generic_only]
    return sorted(hits, key=lambda h: (-h.score, h.company.id))[:request.limit]
