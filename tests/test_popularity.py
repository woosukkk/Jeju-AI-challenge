from datetime import date, timedelta

from trade_itsuda.ingest import demo_companies, import_companies
from trade_itsuda.popularity import popular, record_event
from trade_itsuda.store import connect, initialize


def test_real_events_deduplicated_window_and_scope(tmp_path):
    path = tmp_path / 'db'
    initialize(path)
    import_companies(path, demo_companies(), b'demo', 'demo')
    assert popular(path) == []
    day = date(2026, 11, 17)
    for action in ['view', 'view', 'compare']:
        record_event(path, 'demo-print', 'private-session', action, day)
    record_event(path, 'demo-box', 'other', 'view', day - timedelta(days=30))
    record_event(path, 'demo-box', 'future', 'view', day + timedelta(days=1))
    assert popular(path, as_of=day)[0]['interest_count'] == 1
    assert popular(path, as_of=day)[0]['comparisons'] == 1
    assert len(popular(path, as_of=day)) == 1
    assert popular(path, as_of=day, allowed_ids={'demo-box'}) == []
    with connect(path) as db:
        assert 'private-session' not in str([tuple(r) for r in db.execute('SELECT * FROM events')])
