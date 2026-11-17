"""Agent가 호출하는 데이터 탐색 도구. 숫자는 모두 이 함수들이 로컬 데이터에서 센다."""
from collections import Counter

from .models import Company
from .retrieval import matched_terms, tokens


def matches(company: Company, groups: list[set[str]]) -> bool:
    # 상호(예: '포장마차')는 취급 품목이 아니므로 분류·지역 집계에는 생산품·업종만 쓴다.
    return any(matched_terms(groups, text) for text in (company.products, company.industry))


def list_categories(records: list[Company], keyword: str, region: str = '', limit: int = 15) -> dict:
    """키워드와 관련된 실제 업종 분류와 업소 수. 사용자 표현을 데이터의 분류명으로 바꿀 때 쓴다."""
    groups = tokens(keyword)
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for company in records:
        if region and region not in company.region:
            continue
        if not groups or not matches(company, groups):
            continue
        counts[company.industry] += 1
        product = company.products.split(' ; ')[0]
        bucket = examples.setdefault(company.industry, [])
        if product not in bucket and len(bucket) < 3:
            bucket.append(product)
    return {'keyword': keyword, 'region': region or '전체', 'matched_total': sum(counts.values()),
            'categories': [{'industry': name, 'count': count, 'examples': examples[name]}
                           for name, count in counts.most_common(limit)]}


def count_by_region(records: list[Company], query: str, industry: str = '', limit: int = 10) -> dict:
    """품목 일치 업소가 지역별로 몇 곳인지 센다. 선택 지역에 후보가 없을 때 대안 지역을 알려준다."""
    groups = tokens(query)
    counts: Counter[str] = Counter()
    for company in records:
        if industry and industry not in company.industry and industry not in company.products:
            continue
        if groups and matches(company, groups):
            counts[company.region] += 1
    return {'query': query, 'industry': industry or '전체', 'matched_total': sum(counts.values()),
            'regions': [{'region': name, 'count': count} for name, count in counts.most_common(limit)]}
