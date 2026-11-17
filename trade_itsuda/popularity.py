from datetime import date, timedelta
from hashlib import sha256

from .comparison import today
from .store import connect


def record_event(path, company_id: str, session_id: str, action: str, on_date: date | None = None):
    if action not in {'view', 'compare'} or not session_id or len(session_id) > 200:
        raise ValueError('잘못된 관심 기록입니다.')
    day = on_date or today()
    digest = sha256(session_id.encode()).hexdigest()
    with connect(path) as db:
        if not db.execute('SELECT 1 FROM companies WHERE id=?', (company_id,)).fetchone():
            raise ValueError('등록된 업체만 관심 기록에 포함할 수 있습니다.')
        db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?)', (company_id, digest, day.isoformat(), action))


def popular(path, *, as_of: date | None = None, allowed_ids: set[str] | None = None, limit=5):
    if not 1 <= limit <= 20:
        raise ValueError('조회 개수는 1~20이어야 합니다.')
    end = as_of or today()
    start = end - timedelta(days=29)
    with connect(path) as db:
        rows = db.execute('''SELECT company_id, COUNT(DISTINCT session_hash || day) AS interest_count,
                    SUM(action='view') AS views, SUM(action='compare') AS comparisons, MAX(day) AS last_event
                    FROM events WHERE day BETWEEN ? AND ? GROUP BY company_id
                    ORDER BY interest_count DESC, company_id''', (start.isoformat(), end.isoformat())).fetchall()
    return [dict(row) for row in rows if allowed_ids is None or row['company_id'] in allowed_ids][:limit]


def prune_events(path, as_of: date | None = None):
    cutoff = (as_of or today()) - timedelta(days=35)
    with connect(path) as db:
        db.execute('DELETE FROM events WHERE day<?', (cutoff.isoformat(),))
