import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('make_submission', Path(__file__).resolve().parents[1] / 'scripts' / 'make_submission.py')
assert spec and spec.loader
make_submission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_submission)


def test_submission_rejects_keys_databases_and_environments():
    ok = make_submission.problems
    assert ok('.env.example', b'GEMINI_API_KEY=') == []
    assert ok('app.py', b'print(1)') == []
    for name in ['.env', '.env.local', 'data/jeju_store.sqlite3', '.venv/Scripts/python.exe', 'models/e5/x.bin', 'list.xlsx']:
        assert ok(name, b''), name
    assert ok('docs/MANUAL.md', b'key AIza' + b'x' * 35)
    assert ok('app.py', b'sk-' + b'a' * 30)



def test_evaluation_env_keeps_only_the_openai_key():
    import pytest
    text = ('LLM_PROVIDER=openai\nOPENAI_API_KEY="sk-test-evaluation"\nGEMINI_API_KEY=gem-secret\n'
            'NTS_API_KEY=nts-secret\nALLOW_EXTERNAL_DATA=false\nDATABASE_PATH=C:/Users/me/data.sqlite3\n')
    out = make_submission.evaluation_env(text)
    assert 'OPENAI_API_KEY=sk-test-evaluation' in out and 'ALLOW_EXTERNAL_DATA=true' in out
    assert 'gem-secret' not in out and 'nts-secret' not in out and 'C:/Users' not in out
    assert 'AI_SESSION_LIMIT=30' in out and 'DATABASE_PATH=data/trade_itsuda.sqlite3' in out
    for bad in ['LLM_PROVIDER=gemini\nOPENAI_API_KEY=x', 'LLM_PROVIDER=openai\nOPENAI_API_KEY=',
                'LLM_PROVIDER=openai\nLLM_MODEL=openai\nOPENAI_API_KEY=x']:
        with pytest.raises(ValueError):
            make_submission.evaluation_env(bad)



def test_provider_name_in_model_falls_back_to_default():
    from trade_itsuda.config import model_id
    assert model_id('openai', 'gpt-5.4-mini') == 'gpt-5.4-mini' and model_id(' ', 'gpt-5.4-mini') == 'gpt-5.4-mini'
    assert model_id('gpt-5.4', 'gpt-5.4-mini') == 'gpt-5.4'
