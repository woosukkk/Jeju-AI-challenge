from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Company(Record):
    id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=300)
    products: str = Field(min_length=1, max_length=3000)
    region: str = Field(min_length=1, max_length=200)
    source_name: str = Field(min_length=1, max_length=300)
    source_date: date
    business_number: str = ''
    website: str = ''
    is_demo: bool = False

    @field_validator('business_number')
    @classmethod
    def business_number_format(cls, value: str) -> str:
        value = value.replace('-', '').replace(' ', '')
        if value and (not value.isascii() or not value.isdigit() or len(value) != 10):
            raise ValueError('사업자번호는 숫자 10자리 또는 빈 값이어야 합니다.')
        return value

    @field_validator('website')
    @classmethod
    def website_format(cls, value: str) -> str:
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username:
                raise ValueError('웹사이트는 http/https 주소여야 합니다.')
        return value


class SearchRequest(Record):
    query: str = Field(min_length=1, max_length=2000)
    region: str = Field(default='', max_length=200)
    industry: str = Field(default='', max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class Quote(Record):
    id: str = Field(min_length=1, max_length=160)
    company_id: str = Field(min_length=1, max_length=160)
    company_name: str = Field(min_length=1, max_length=200)
    item: str = Field(min_length=1, max_length=300)
    specification: str = Field(min_length=1, max_length=1000)
    unit: str = Field(min_length=1, max_length=50)
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency: str = Field(default='KRW', pattern=r'^[A-Z]{3}$')
    tax_included: bool | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    shipping: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    extra_cost: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    minimum_order: Decimal | None = Field(default=None, gt=0)
    lead_days: int | None = Field(default=None, ge=0)
    issued_at: date | None = None
    valid_until: date | None = None
    source_name: str = Field(default='사용자 입력', min_length=1, max_length=300)
    confirmed: bool = False

    @field_validator('valid_until')
    @classmethod
    def validity_order(cls, value, info):
        issued = info.data.get('issued_at')
        if value and issued and value < issued:
            raise ValueError('견적 유효기간이 발행일보다 앞설 수 없습니다.')
        return value


class QuoteExtraction(Record):
    company_name: str | None = None
    item: str | None = None
    specification: str | None = None
    unit: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    tax_included: bool | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    shipping: Decimal | None = Field(default=None, ge=0)
    extra_cost: Decimal | None = Field(default=None, ge=0)
    minimum_order: Decimal | None = Field(default=None, gt=0)
    lead_days: int | None = Field(default=None, ge=0)
    issued_at: date | None = None
    valid_until: date | None = None

    @field_validator('currency')
    @classmethod
    def currency_format(cls, value):
        if value is not None and (len(value) != 3 or not value.isascii() or not value.isupper()):
            raise ValueError('통화는 KRW 등 3자리 대문자여야 합니다.')
        return value
