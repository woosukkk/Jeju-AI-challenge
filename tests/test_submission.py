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
