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
    return groups


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
    filtered = [c for c in records if (not request.region or request.region in c.region)
                and (not request.industry or request.industry in c.industry)]
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
    for index, company in enumerate(filtered):
        evidence = []
        weight = 0
        for label, text, multiplier in [('생산품', company.products, 3), ('업종', company.industry, 2), ('업체명', company.name, 1)]:
            matched = matched_terms(terms, text)
            if matched:
                weight += multiplier * len(matched)
                evidence.append(f'{label}에서 일치: {", ".join(matched)}')
        if weight == 0 and encoder is None:
            continue
        if encoder is not None and weight == 0:
            evidence.append('의미 검색 탐색 후보: 실제 취급 품목은 업체 확인 필요')
        typed_name = re.sub(r'\s+', '', company.name.lower()) in re.sub(r'\s+', '', request.query.lower())
        # 상호에 품목 낱말만 들어간 업소(예: '○○박스' 미용실)는 취급 근거가 아니므로 뺀다.
        # 사용자가 업체명을 통째로 입력한 경우(기존 거래처 찾기)만 남기고 맨 앞에 둔다.
        if evidence and all(reason.startswith('업체명') for reason in evidence) and not typed_name:
            continue
        score = float(weight + semantic[index] + (10 if typed_name and evidence else 0))
        hits.append(SearchHit(company, score, evidence, '키워드 + 의미' if encoder else '키워드'))
    return sorted(hits, key=lambda h: (-h.score, h.company.id))[:request.limit]
