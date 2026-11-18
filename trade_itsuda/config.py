import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_path: Path
    provider: str
    model: str
    llm_key: str = field(repr=False)
    nts_key: str = field(repr=False)
    allow_external_data: bool = False
    # 한 사용자(브라우저 세션)가 쓸 수 있는 AI 작업 수(검색·문의 질문 업체 1곳·견적 추출·비교 해설을 각각 1회로 센다).
    # 넘으면 키워드 검색·직접 입력으로 이어간다. 0이면 AI를 쓰지 않는다.
    ai_session_limit: int = 30


def settings() -> Settings:
    load_dotenv(override=False)
    provider = os.getenv('LLM_PROVIDER', 'openai').strip().lower()
    if provider not in {'openai', 'gemini'}:
        raise ValueError('LLM_PROVIDER는 openai 또는 gemini여야 합니다.')
    # gemini-3.5-flash-lite: 2026-11-17 실호출로 검색 Agent·해설·문의·견적 추출을 확인한 모델.
    # gemini-3.8-flash는 같은 날 503(수요 과다)과 35초 시간 초과가 반복되어 기본값에서 뺐다.
    default_model = 'gemini-3.5-flash-lite' if provider == 'gemini' else 'gpt-5.4-mini'
    return Settings(
        database_path=Path(os.getenv('DATABASE_PATH', 'data/trade_itsuda.sqlite3')),
        provider=provider,
        model=os.getenv('LLM_MODEL', '').strip() or default_model,
        llm_key=os.getenv('GEMINI_API_KEY' if provider == 'gemini' else 'OPENAI_API_KEY', ''),
        nts_key=os.getenv('NTS_API_KEY', ''),
        allow_external_data=os.getenv('ALLOW_EXTERNAL_DATA', 'false').lower() == 'true',
        ai_session_limit=session_limit(os.getenv('AI_SESSION_LIMIT', '30')),
    )


def session_limit(value: str) -> int:
    try:
        limit = int(value.strip())
    except ValueError:
        raise ValueError('AI_SESSION_LIMIT는 0 이상의 정수여야 합니다.') from None
    if limit < 0:
        raise ValueError('AI_SESSION_LIMIT는 0 이상의 정수여야 합니다.')
    return limit
