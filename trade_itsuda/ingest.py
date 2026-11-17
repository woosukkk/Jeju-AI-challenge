import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd
from pydantic import ValidationError

from .models import Company
from .store import connect

ALIASES = {
    'ent_nm': 'name', '기업명': 'name', 'ksic10_biz_nm': 'industry', '업종명': 'industry',
    'main_products': 'products', '주요생산품': 'products', 'address_emd': 'region',
    '주소_읍면동': 'region', 'base_date': 'source_date', '데이터 기준일': 'source_date',
    'biz_num': 'business_number', '사업자번호': 'business_number', 'ked_code': 'id', 'kedcd': 'id',
}


@dataclass
class ParseResult:
    records: list[Company]
    # 제외 사유 → 원본 행 번호(머리글 = 1행). 데이터 활용 명세의 결측·제외 행 수 근거.
    skipped: dict[str, list[int]] = field(default_factory=dict)

    @property
    def skipped_count(self) -> int:
        return sum(len(rows) for rows in self.skipped.values())


def parse_file(content: bytes, filename: str, source_name: str, source_date: date | None = None,
               sheet_name: str | int = 0) -> ParseResult:
    if not content or len(content) > 20 * 1024 * 1024:
        raise ValueError('비어 있거나 20MB를 초과하는 파일입니다. 허용된 기업 표를 나눠 반입하세요.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        try:
            frame = pd.read_csv(io.BytesIO(content), encoding='utf-8-sig', dtype=str, keep_default_na=False, header=None)
        except UnicodeDecodeError:
            frame = pd.read_csv(io.BytesIO(content), encoding='cp949', dtype=str, keep_default_na=False, header=None)
    elif suffix == '.xlsx':
        try:
            with ZipFile(io.BytesIO(content)) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError('XLSX 압축 해제 크기가 100MB를 초과합니다. 기업 표를 나눠 반입하세요.')
            frame = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, dtype=str, keep_default_na=False, header=None)
        except (BadZipFile, KeyError):
            raise ValueError('올바른 XLSX 파일을 선택하세요.') from None
        except ValueError:
            raise
        except Exception:
            raise ValueError('XLSX 내용을 읽을 수 없습니다. 손상 여부와 시트를 확인하세요.') from None
    else:
        raise ValueError('CSV 또는 XLSX 기업 테이블을 선택하세요.')
    if len(frame) < 2 or len(frame) > 100_001:
        raise ValueError('기업 표는 1~100,000행이어야 합니다.')
    columns = [ALIASES.get(str(column).strip(), str(column).strip()) for column in frame.iloc[0]]
    if len(set(columns)) != len(columns):
        raise ValueError('동일 필드로 대응되는 열이 여러 개입니다. 중복 열을 확인하세요.')
    frame = frame.iloc[1:].reset_index(drop=True)
    frame.columns = pd.Index(columns)
    missing = {'name', 'industry', 'products', 'region'} - set(frame.columns)
    if missing:
        raise ValueError('실제 기업 테이블에 필요한 열이 없습니다: ' + ', '.join(sorted(missing)))
    source_name = source_name.strip()
    if not source_name:
        raise ValueError('출처명을 입력하세요.')
    records = []
    ids = set()
    skipped: dict[str, list[int]] = {}
    for index, row in enumerate(frame.to_dict('records'), start=2):
        raw = {key: str(row.get(key, '')).strip() for key in
               ('name', 'industry', 'products', 'region', 'business_number', 'website')}
        raw_date = str(row.get('source_date', '')).strip() or source_date or ''
        if isinstance(raw_date, str) and len(raw_date) == 8 and raw_date.isdigit():
            raw_date = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}'
        business_id = raw['business_number'].replace('-', '').replace(' ', '')
        identity = str(row.get('id', '')).strip() or business_id or f"{raw['name']}|{raw['region']}"
        company_id = hashlib.sha256(f'{source_name}|{identity}'.encode()).hexdigest()[:24]
        try:
            company = Company(id=company_id, source_name=source_name, source_date=raw_date, **raw)
        except ValidationError as error:
            skipped.setdefault(skip_reason(error), []).append(index)
            continue
        if company_id in ids:
            skipped.setdefault('같은 기업 식별자 반복 (첫 행만 사용)', []).append(index)
            continue
        ids.add(company_id)
        records.append(company)
    if not records:
        summary = ', '.join(f'{reason} {len(rows)}행' for reason, rows in skipped.items())
        raise ValueError('가져올 수 있는 기업 행이 없습니다: ' + summary)
    return ParseResult(records, skipped)


FIELD_LABELS = {'name': '업체명', 'industry': '업종', 'products': '생산품', 'region': '지역',
                'source_date': '데이터 기준일', 'business_number': '사업자번호', 'website': '웹사이트'}


def skip_reason(error: ValidationError) -> str:
    fields = sorted({FIELD_LABELS.get(str(item['loc'][0]), str(item['loc'][0])) for item in error.errors() if item['loc']})
    return '빈 값 또는 형식 오류: ' + ', '.join(fields)


def import_companies(path, records: list[Company], content: bytes, source_name: str) -> int:
    if not records or len({record.id for record in records}) != len(records):
        raise ValueError('기업 목록이 비었거나 식별자가 중복됩니다.')
    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        # shortcut: 최신 스냅샷만 보관, 이력 비교가 필요해지면 버전 테이블로 확장.
        for record in records:
            previous = db.execute('SELECT payload FROM companies WHERE id=?', (record.id,)).fetchone()
            if previous and Company.model_validate_json(previous['payload']).source_date > record.source_date:
                raise ValueError('더 오래된 자료로 기존 기업정보를 덮어쓸 수 없습니다.')
            db.execute('INSERT INTO companies VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (record.id, record.model_dump_json()))
        db.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?,?)', (digest, source_name, now, len(records)))
    return len(records)


def demo_companies() -> list[Company]:
    entries = [
        ('print', '가상 한라라벨', '인쇄업', '제품 라벨 스티커 인쇄 패키지 디자인', '제주시 노형동'),
        ('box', '가상 제주포장', '포장재 제조업', '종이 상자 박스 선물 포장재', '제주시 한림읍'),
        ('glass', '가상 돌담용기', '용기 도매업', '유리병 잼병 식품 용기', '서귀포시 대정읍'),
        ('clean', '가상 바람시설', '시설 관리업', '사업장 청소 시설 관리', '서귀포시 동홍동'),
    ]
    return [Company(id=f'demo-{key}', name=name, industry=industry, products=products, region=region,
                    source_name='가상 기능 검증 데이터', source_date='2026-11-17', is_demo=True,
                    website=f'https://{key}.invalid') for key, name, industry, products, region in entries]
