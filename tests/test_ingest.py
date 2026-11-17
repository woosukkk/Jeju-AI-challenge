import pytest

from trade_itsuda.ingest import demo_companies, import_companies, parse_file
from trade_itsuda.store import companies, import_history, initialize


def test_source_aliases_dates_and_digest(tmp_path):
    blob = 'ent_nm,ksic10_biz_nm,main_products,address_emd,base_date,biz_num\n가상인쇄,인쇄,라벨,제주시,20251101,\n'.encode('utf-8-sig')
    parsed = parse_file(blob, '기업.csv', '승인된 출처')
    assert str(parsed[0].source_date) == '2025-11-01'
    path = tmp_path / 'test.db'
    initialize(path)
    assert import_companies(path, parsed, blob, '승인된 출처') == 1
    assert len(import_history(path)[0]['sha256']) == 64


def test_validation_rejects_spec_sheet_and_duplicate_rows():
    with pytest.raises(ValueError, match='필요한 열'):
        parse_file(b'No,Column,Type\n1,name,STRING', 'spec.csv', '명세')
    row = '가상,인쇄,라벨,제주시,20251101'
    with pytest.raises(ValueError, match='반복'):
        parse_file(('name,industry,products,region,source_date\n' + row + '\n' + row).encode(), 'x.csv', '출처')


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
