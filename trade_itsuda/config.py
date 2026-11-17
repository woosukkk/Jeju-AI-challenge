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


def settings() -> Settings:
    load_dotenv(override=False)
    provider = os.getenv('LLM_PROVIDER', 'openai').strip().lower()
    if provider not in {'openai', 'gemini'}:
        raise ValueError('LLM_PROVIDER는 openai 또는 gemini여야 합니다.')
    default_model = 'gemini-3.8-flash' if provider == 'gemini' else 'gpt-5.4-mini'
    return Settings(
        database_path=Path(os.getenv('DATABASE_PATH', 'data/trade_itsuda.sqlite3')),
        provider=provider,
        model=os.getenv('LLM_MODEL', '').strip() or default_model,
        llm_key=os.getenv('GEMINI_API_KEY' if provider == 'gemini' else 'OPENAI_API_KEY', ''),
        nts_key=os.getenv('NTS_API_KEY', ''),
        allow_external_data=os.getenv('ALLOW_EXTERNAL_DATA', 'false').lower() == 'true',
    )
