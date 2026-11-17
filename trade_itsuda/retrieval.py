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


def tokens(query: str) -> set[str]:
    words = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', query.lower()))
    stop = {'업체', '거래처', '찾아줘', '찾고', '싶어', '필요해', '있는', '추천', '제주', '제주도'}
    words -= stop
    # shortcut: 작은 품목 사전만 확장, 실제 검색 실패 사례가 쌓이면 사전을 보완.
    for concept, variants in {'포장': ['박스', '상자', '패키지'], '라벨': ['스티커'],
                              '용기': ['유리병', '잼병'], '청소': ['시설 관리']}.items():
        if any(concept in word for word in words.copy()):
            words.update([concept, *variants])
    return words


def load_encoder(model_path: str):
    if not Path(model_path).is_dir():
        raise ValueError('로컬 임베딩 모델 폴더가 없습니다. 기본 키워드 검색을 사용하세요.')
    try:
        from sentence_transformers import SentenceTransformer
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
            matched = sorted(term for term in terms if term in text.lower())
            if matched:
                weight += multiplier * len(matched)
                evidence.append(f'{label}에서 일치: {", ".join(matched)}')
        if weight == 0 and encoder is None:
            continue
        if encoder is not None and weight == 0:
            evidence.append('의미 검색 탐색 후보: 실제 취급 품목은 업체 확인 필요')
        score = float(weight + semantic[index])
        hits.append(SearchHit(company, score, evidence, '키워드 + 의미' if encoder else '키워드'))
    return sorted(hits, key=lambda h: (-h.score, h.company.id))[:request.limit]
