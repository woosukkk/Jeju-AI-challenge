import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Company, Quote


@contextmanager
def connect(path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path):
    with connect(path) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imports(
                sha256 TEXT PRIMARY KEY, source_name TEXT NOT NULL,
                imported_at TEXT NOT NULL, row_count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS business_status(
                company_id TEXT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                payload TEXT, checked_at TEXT, attempted_at TEXT NOT NULL, error TEXT);
            CREATE TABLE IF NOT EXISTS events(
                company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                session_hash TEXT NOT NULL, day TEXT NOT NULL, action TEXT NOT NULL,
                PRIMARY KEY(company_id, session_hash, day, action));
        ''')


def companies(path) -> list[Company]:
    with connect(path) as db:
        return [Company.model_validate_json(row['payload']) for row in db.execute('SELECT payload FROM companies ORDER BY id')]


def company(path, company_id: str) -> Company | None:
    with connect(path) as db:
        row = db.execute('SELECT payload FROM companies WHERE id=?', (company_id,)).fetchone()
    return Company.model_validate_json(row['payload']) if row else None


def save_quotes(path, quotes: list[Quote]):
    payloads = [(quote.id, quote.model_dump_json()) for quote in quotes]
    with connect(path) as db:
        db.executemany('INSERT INTO quotes VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', payloads)


def quotes(path) -> list[Quote]:
    with connect(path) as db:
        return [Quote.model_validate_json(row['payload']) for row in db.execute('SELECT payload FROM quotes ORDER BY id')]


def delete_quote(path, quote_id: str):
    with connect(path) as db:
        db.execute('DELETE FROM quotes WHERE id=?', (quote_id,))


def import_history(path):
    with connect(path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM imports ORDER BY imported_at DESC')]


def read_status(path, company_id: str):
    with connect(path) as db:
        row = db.execute('SELECT * FROM business_status WHERE company_id=?', (company_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result['payload'] = json.loads(result['payload']) if result['payload'] else None
    return result
