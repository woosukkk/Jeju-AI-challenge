"""실제 반입 데이터로 검색 품질·소요 시간을 잰다(TODO P1-02).

판정 기준(실행 전에 정함): 질의마다 '이 말이 업종 또는 생산품 칸에 있으면 적합'인 단어를 정해 두고, 상위 5곳 중
적합한 곳의 비율을 센다. 사람의 판정이 아니라 자동 근사치다. 후보가 없어야 맞는 질의는 0곳일 때 정답으로 본다.

사용:
  .venv\Scripts\python.exe scripts\measure_search.py            # 키워드 검색만 (외부 전송 없음)
  .venv\Scripts\python.exe scripts\measure_search.py --agent    # AI Agent도 함께 (.env 키·외부 전송 허용 필요, 요금 발생)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_itsuda import store  # noqa: E402
from trade_itsuda.agent import AgentError, run_agent  # noqa: E402
from trade_itsuda.config import settings  # noqa: E402
from trade_itsuda.models import SearchRequest  # noqa: E402
from trade_itsuda.retrieval import SearchHit, search  # noqa: E402

# (질의, 지역, 적합 판정 단어). 판정 단어가 비어 있으면 '후보 없음'이 정답인 질의.
CASES: list[tuple[str, str, list[str]]] = [
    ('가게 간판을 새로 달고 싶어요', '', ['간판']),
    ('가게 간판을 새로 달고 싶어요', '서귀포시', ['간판']),
    ('택배 박스 포장재가 필요해요', '', ['포장']),
    ('택배 박스 포장재가 필요해요', '제주시 이도1동', ['포장']),
    ('명함과 전단지를 인쇄하고 싶어요', '', ['인쇄']),
    ('가게 로고 디자인을 맡기고 싶어요', '', ['디자인']),
    ('매장 청소 업체를 찾아요', '', ['청소']),
    ('세무 기장을 맡길 곳', '', ['세무', '회계']),
    ('가게 인테리어 공사', '', ['인테리어', '실내']),
    ('페인트와 건축 자재를 사고 싶어요', '', ['건설자재', '건축자재', '페인트']),
    ('식당 업소용 냉장고 수리', '', ['수리']),
    ('반도체 웨이퍼 장비', '', []),
]


def relevant(hit: SearchHit, words: list[str]) -> bool:
    text = f'{hit.company.industry} {hit.company.products}'
    return any(word in text for word in words)


def score(hits: list[SearchHit], words: list[str]) -> str:
    if not words:
        return '정답(0곳)' if not hits else f'오답({len(hits)}곳)'
    if not hits:
        return '0곳'
    return f'{sum(relevant(h, words) for h in hits)}/{len(hits)}'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--agent', action='store_true', help='AI Agent 검색도 측정 (요금 발생)')
    parser.add_argument('--output', type=Path, default=Path('outputs/search_measure.json'))
    parser.add_argument('--pause', type=float, default=0, help='Agent 질의 사이에 쉴 초 (무료 키의 분당 호출 한도 대비)')
    parser.add_argument('--first', type=int, default=1, help='이 번호의 질의부터 측정 (1부터)')
    args = parser.parse_args(argv)
    config = settings()
    started = time.perf_counter()
    records = store.companies(config.database_path)
    load_seconds = time.perf_counter() - started
    print(f'데이터 {len(records):,}곳, DB 읽기 {load_seconds:.2f}초 ({config.database_path})')
    rows = []
    for number, (query, region, words) in enumerate(CASES, start=1):
        if number < args.first:
            continue
        if args.agent and args.pause and rows:
            time.sleep(args.pause)
        request = SearchRequest(query=query, region=region)
        started = time.perf_counter()
        hits = search(records, request)
        row = {'query': query, 'region': region or '전체', 'keyword_seconds': round(time.perf_counter() - started, 3),
               'keyword': score(hits, words), 'keyword_top': [h.company.industry for h in hits]}
        if args.agent:
            started = time.perf_counter()
            try:
                result = run_agent(config, records, request)
                row['agent'] = score(result.hits, words)
                row['agent_tools'] = [step.get('tool') for step in result.trace]
            except AgentError as error:
                row['agent'] = f'실패: {error}'
            row['agent_seconds'] = round(time.perf_counter() - started, 1)
        row['number'] = number
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'companies': len(records), 'load_seconds': round(load_seconds, 2),
                                       'model': config.model if args.agent else None, 'rows': rows},
                                      ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'저장: {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
