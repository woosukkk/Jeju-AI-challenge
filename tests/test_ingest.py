import pytest

from trade_itsuda.ingest import demo_companies, import_companies, parse_file
from trade_itsuda.models import SearchRequest
from trade_itsuda.retrieval import search
from trade_itsuda.store import companies, import_history, initialize


def test_source_aliases_dates_and_digest(tmp_path):
    blob = 'ent_nm,ksic10_biz_nm,main_products,address_emd,base_date,biz_num\n가상인쇄,인쇄,라벨,제주시,20251101,\n'.encode('utf-8-sig')
    parsed = parse_file(blob, '기업.csv', '승인된 출처')
    assert str(parsed.records[0].source_date) == '2025-11-01'
    assert parsed.skipped == {}
    path = tmp_path / 'test.db'
    initialize(path)
    assert import_companies(path, parsed.records, blob, '승인된 출처') == 1
    assert len(import_history(path)[0]['sha256']) == 64


def test_validation_rejects_spec_sheet_and_skips_duplicate_rows():
    with pytest.raises(ValueError, match='필요한 열'):
        parse_file(b'No,Column,Type\n1,name,STRING', 'spec.csv', '명세')
    row = '가상,인쇄,라벨,제주시,20251101'
    parsed = parse_file(('name,industry,products,region,source_date\n' + row + '\n' + row).encode(), 'x.csv', '출처')
    assert len(parsed.records) == 1
    assert parsed.skipped == {'같은 기업 식별자 반복 (첫 행만 사용)': [3]}


def test_invalid_rows_are_skipped_with_reasons():
    raw = ('name,industry,products,region,source_date\n'
           '가상인쇄,인쇄,라벨,제주시,20251101\n'
           '빈생산품,인쇄,,제주시,20251101\n'
           '날짜오류,인쇄,라벨,제주시,2025-13-40\n'
           '가상용기,도매,유리병,서귀포시,20251101\n').encode()
    parsed = parse_file(raw, 'x.csv', '출처')
    assert [c.name for c in parsed.records] == ['가상인쇄', '가상용기']
    assert parsed.skipped == {'빈 값 또는 형식 오류: 생산품': [3], '빈 값 또는 형식 오류: 데이터 기준일': [4]}
    assert parsed.skipped_count == 2
    with pytest.raises(ValueError, match='가져올 수 있는 기업 행이 없습니다'):
        parse_file('name,industry,products,region\n가상,인쇄,,제주시\n'.encode(), 'x.csv', '출처')


def test_jeju_store_table_columns_are_combined():
    from datetime import date
    header = ('상호명,상권업종대분류명,상권업종중분류명,상권업종소분류명,표준산업분류명,시도명,시군구명,행정동명,법정동명,'
              '행정동코드,법정동코드,지번주소,도로명주소,신우편번호,경도,위도\n')
    def row(name, mid, small, standard, emd, lot):
        return (f'{name},소매,{mid},{small},{standard},제주특별자치도,제주시,{emd},{emd},5011010300,5011010300,'
                f'제주특별자치도 제주시 {emd} {lot},제주특별자치도 제주시 중앙로,63194,126.5,33.5\n')
    raw = (header + row('가상포장', '종합 소매', '포장재', '포장재료 소매업', '이도1동', '1-1')
           + row('가상포장', '종합 소매', '포장재', '포장재료 소매업', '이도1동', '2-5')
           + row('가상인쇄', '인쇄', '인쇄', '인쇄', '노형동', '3-2')
           + row('빈업종', '종합 소매', '', '', '노형동', '4-4')).encode('cp949')
    parsed = parse_file(raw, '제주특별자치도 상가(상권) 정보.csv', '제주데이터허브 상가(상권) 정보', date(2025, 9, 18))
    first = parsed.records[0]
    assert (first.name, first.industry, first.products, first.region) == ('가상포장', '종합 소매', '포장재 / 포장재료 소매업', '제주시 이도1동')
    assert first.source_date == date(2025, 9, 18)
    # 같은 이름·같은 동이라도 지번이 다르면 다른 업소로 보관한다.
    assert len({c.id for c in parsed.records[:2]}) == 2
    assert parsed.records[2].products == '인쇄'
    assert parsed.skipped == {'빈 값 또는 형식 오류: 생산품': [5]}
    hits = search(parsed.records, SearchRequest(query='포장 박스가 필요해요', region='이도1동'))
    assert [h.company.name for h in hits] == ['가상포장', '가상포장']


def test_import_rolls_back_all_rows_on_older_snapshot(tmp_path):
    path = tmp_path / 'test.db'
    initialize(path)
    original = demo_companies()[0]
    import_companies(path, [original], b'first', '합성')
    new = demo_companies()[1]
    older = original.model_copy(update={'source_date': original.source_date.replace(year=2020)})
    with pytest.raises(ValueError, match='오래된'):
        import_companies(path, [new, older], b'bad', '합성')
    assert [record.id for record in companies(path)] == [original.id]
    assert len(import_history(path)) == 1


def test_duplicate_headers_and_invalid_xlsx_rejected():
    from trade_itsuda.ingest import parse_file
    import pytest
    with pytest.raises(ValueError, match='중복 열'):
        parse_file('name,name,industry,products,region\n가,나,인쇄,라벨,제주'.encode(), 'a.csv', 'test')
    with pytest.raises(ValueError, match='XLSX'):
        parse_file(b'not-a-zip', 'a.xlsx', 'test')


def test_file_date_takes_priority_over_fallback():
    from datetime import date
    from trade_itsuda.ingest import parse_file
    raw = 'name,industry,products,region,source_date\n가상,인쇄,라벨,제주,2020-07-31'.encode()
    assert parse_file(raw, 'a.csv', 'test', date(2026, 1, 1)).records[0].source_date == date(2020, 7, 31)
