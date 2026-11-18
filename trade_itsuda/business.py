import json
from datetime import datetime, timedelta, timezone

import httpx

from .config import Settings
from .models import Company
from .store import connect, read_status

ENDPOINT = 'https://api.odcloud.kr/api/nts-businessman/v1/status'


LABELS = {'01': '계속사업자', '02': '휴업자', '03': '폐업자'}


def business_number(value: str) -> str:
    """사업자번호를 숫자 10자리로 정리한다. 형식이 틀리면 ValueError."""
    number = value.replace('-', '').replace(' ', '').strip()
    if not (number.isascii() and number.isdigit() and len(number) == 10):
        raise ValueError('사업자번호는 숫자 10자리입니다(예: 123-45-67890).')
    return number


def lookup_status(number: str, config: Settings, *, post=None, now: datetime | None = None) -> dict:
    """국세청 상태조회를 한 번 부른다. 저장·캐시 없이 결과만 돌려준다(5단계 '사업자 상태 확인'용).

    돌려주는 값: b_no, code, label(계속사업자·휴업자·폐업자·확인 불가), end_dt, checked_at. 실패하면 ValueError.
    """
    number = business_number(number)
    if not config.allow_external_data or not config.nts_key:
        raise ValueError('국세청 API 키와 외부 전송 허용 설정이 필요합니다.')
    try:
        response = (post or httpx.post)(ENDPOINT, params={'serviceKey': config.nts_key}, json={'b_no': [number]}, timeout=10)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        raise ValueError('국세청 조회에 실패했습니다. 잠시 뒤 다시 시도하세요.') from None
    data = body.get('data') or []
    if body.get('status_code') != 'OK' or len(data) != 1 or data[0].get('b_no') != number:
        raise ValueError('국세청 응답을 확인하지 못했습니다.')
    code = data[0].get('b_stt_cd')
    return {'b_no': number, 'code': code, 'label': LABELS.get(code, '확인 불가'), 'end_dt': data[0].get('end_dt') or None,
            'checked_at': (now or datetime.now(timezone.utc)).isoformat()}


def refresh_status(path, company: Company, config: Settings, *, now=None, post=None):
    now = now or datetime.now(timezone.utc)
    cached = read_status(path, company.id)
    if company.is_demo or not company.business_number:
        return {'payload': None, 'checked_at': None, 'error': '사업자번호가 없거나 가상 데이터이므로 조회하지 않습니다.'}
    if not config.allow_external_data or not config.nts_key:
        return cached or {'payload': None, 'checked_at': None, 'error': '국세청 API 키와 외부 전송 허용 설정이 필요합니다.'}
    same_number = cached and cached['payload'] and cached['payload'].get('b_no') == company.business_number
    if same_number and cached['checked_at'] and now - datetime.fromisoformat(cached['checked_at']) < timedelta(hours=24):
        return cached
    if cached and (same_number or not cached['payload']) and now - datetime.fromisoformat(cached['attempted_at']) < timedelta(minutes=5):
        return cached
    payload = cached['payload'] if same_number else None
    checked_at = cached['checked_at'] if same_number else None
    error = None
    try:
        response = (post or httpx.post)(ENDPOINT, params={'serviceKey': config.nts_key},
                                       json={'b_no': [company.business_number]}, timeout=10)
        response.raise_for_status()
        body = response.json()
        if body.get('status_code') != 'OK' or len(body.get('data', [])) != 1:
            raise ValueError()
        data = body['data'][0]
        if data.get('b_no') != company.business_number:
            raise ValueError()
        code = data.get('b_stt_cd')
        payload = {'b_no': company.business_number, 'code': code,
                   'label': LABELS.get(code, '확인 불가'),
                   'end_dt': data.get('end_dt') or None}
        checked_at = now.isoformat()
    except Exception:
        error = '국세청 조회 실패: 이전 성공 결과가 있으면 그대로 표시합니다. 5분 뒤 다시 시도할 수 있습니다.'
    with connect(path) as db:
        db.execute('''INSERT INTO business_status VALUES(?,?,?,?,?) ON CONFLICT(company_id)
                      DO UPDATE SET payload=excluded.payload, checked_at=excluded.checked_at,
                      attempted_at=excluded.attempted_at, error=excluded.error''',
                   (company.id, json.dumps(payload, ensure_ascii=False) if payload else None, checked_at, now.isoformat(), error))
    return read_status(path, company.id)
