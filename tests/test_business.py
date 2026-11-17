from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from trade_itsuda.business import ENDPOINT, refresh_status
from trade_itsuda.config import Settings
from trade_itsuda.ingest import demo_companies, import_companies
from trade_itsuda.store import initialize


def test_status_ttl_failure_keeps_success_and_key_not_stored(tmp_path):
    path = tmp_path / 'db'
    initialize(path)
    company = demo_companies()[0].model_copy(update={'is_demo': False, 'business_number': '1234567890'})
    import_companies(path, [company], b'test', 'test')
    config = Settings(Path(path), 'openai', 'x', '', 'private-nts-key', True)
    calls = []
    def post(url, **kwargs):
        assert url == ENDPOINT
        assert kwargs['json'] == {'b_no': ['1234567890']}
        calls.append(url)
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'status_code': 'OK', 'data': [{'b_no': '1234567890', 'b_stt_cd': '01'}]})
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    first = refresh_status(path, company, config, now=now, post=post)
    assert first['payload']['label'] == '계속사업자'
    assert refresh_status(path, company, config, now=now + timedelta(hours=1), post=post) == first
    assert len(calls) == 1
    def fail(*args, **kwargs):
        raise RuntimeError('private-nts-key must not be persisted')
    failed = refresh_status(path, company, config, now=now + timedelta(days=2), post=fail)
    assert failed['checked_at'] == first['checked_at']
    assert failed['error'] and 'private-nts-key' not in str(failed)


def test_demo_and_external_disabled_never_call(tmp_path):
    path = tmp_path / 'db'
    initialize(path)
    config = Settings(path, 'openai', 'x', '', '', False)
    def fail(*args, **kwargs):
        raise AssertionError('network must not run')
    assert refresh_status(path, demo_companies()[0], config, post=fail)['payload'] is None
