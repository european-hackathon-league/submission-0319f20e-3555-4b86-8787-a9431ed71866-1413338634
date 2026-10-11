"""Import contract tests use synthetic inputs; original BMW data stays local."""
import io
import json
from datetime import datetime
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from server import importers
from server.importers import file_scopes, parse_file, parse_html, parse_scopes


def workbook_bytes(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    target = io.BytesIO()
    workbook.save(target)
    return target.getvalue()


def pdf_bytes(texts, password=None):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 20 250 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = stream
    if password is not None:
        writer.encrypt(password, algorithm='AES-256')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_feedback_preserves_exact_location_metadata_and_date_and_scope():
    data = workbook_bytes({'Feedback_Explorer': [
        ['ID', 'Source', 'Country', 'Derivate (e-code)', 'Customer Feedback', 'Vfc level2 Name', 'Feedback Type', 'Date'],
        ['G60-1', 'Source B', 'USA', 'G60', 'The phone charger is slow.', 'Phone charging', 'Difficult to Use', datetime(2025, 7, 3)],
        ['G60-2', 'Source B', 'CN', 'G60', 'Different market.', 'Other', 'Likes', None],
        ['G70-1', 'Source C', 'US', 'G70', 'Different car.', 'Other', 'Likes', None],
        ['G60-1', 'Source B', 'US', 'G60', 'The phone charger is slow.', 'Phone charging', 'Wants', None],
    ]})
    records = parse_file('G60_feedback.xlsx', data, 'g60', 'USA')
    assert len(records) == 2  # Keep different classification rows; dedup belongs to storage.
    assert records[0]['content'] == 'The phone charger is slow.'
    assert records[0]['location'] == {'sheet': 'Feedback_Explorer', 'row': 2, 'header_row': 1}
    assert records[0]['observed_at'] == '2025-07-03T00:00:00'
    assert records[0]['metadata']['feedback_id'] == 'G60-1'
    assert records[0]['metadata']['topic'] == 'Phone charging'
    assert records[0]['metadata']['sentiment'] == 'Difficult to Use'
    assert records[0]['metadata']['provenance'] == 'Source B'
    assert records[0]['metadata']['columns']['Country'] == 'USA'
    assert records[1]['observed_at'] is None
    assert records[1]['metadata']['date_status'] == 'absent'


def test_studies_handle_us_vehicle_columns_and_topic_sections():
    data = workbook_bytes({'US_2025': [
        ['Charging', None, 'BMW 5 Series G60', 'BMW 7 Series G70'],
        ['Sample total', '% of column, sample base', 1, 1],
        ['Excellent', '% of column, sample base', .4, .3],
        ['Seating', None, None, None],
        ['I Love It', '% of column, sample base', .2, .5],
    ]})
    records = parse_file('F70_G60_G68_G70_customer_studies.xlsx', data)
    assert len(records) == 3
    assert records[-1]['location'] == {'sheet': 'US_2025', 'row': 5, 'column': 3, 'cell': 'C5', 'header_row': 1, 'topic_row': 4}
    assert records[-1]['metadata']['topic'] == 'Seating'
    assert records[-1]['metadata']['value'] == .2
    assert records[-1]['metadata']['record_type'] == 'study_aggregate'
    assert records[-1]['metadata']['reporting_year'] == 2025
    assert records[-1]['observed_at'] is None
    assert records[-1]['metadata']['date_status'] == 'period_only'
    assert parse_file('studies.xlsx', data, market='CN') == []


def test_studies_country_headers_forward_fill_only_their_vehicle_columns():
    data = workbook_bytes({'CN_EU_2025': [
        [None, 'Dataset country'],
        [None, 'China', None, 'EU', None, None],
        ['Overall satisfaction', 'BMW 5 Series G68', 'BMW 7 Series G70', 'BMW 1 Series F70', 'BMW 5 Series G60', 'BMW 7 Series G70'],
        ['Mean', 8.1, 9.2, 8.3, 7.4, 6.5],
        ['Interior', None, None, None, None, None],
        ['Mean', 8.2, 9.3, 8.4, 7.5, 6.6],
    ]})
    assert parse_file('studies.xlsx', data) == []
    eu = parse_file('studies.xlsx', data, vehicle='G60', market='EU')
    assert [record['metadata']['value'] for record in eu] == [7.4, 7.5]
    china = parse_file('studies.xlsx', data, vehicle='G70', market='CN')
    assert china[0]['location']['cell'] == 'C4'
    assert china[0]['metadata']['value'] == 9.2


def test_sales_preserve_combined_vehicle_scope_and_years_without_inventing_dates():
    header = ['market', 'market_code', 'volume_2024', 'volume_2030']
    data = workbook_bytes({'F70': [header, ['USA', 'US', 0, 0]], 'G60_G68': [header, ['Europe', 'EU', 500, 600], ['USA', 'US', 750, 800]]})
    records = parse_file('sales_volumes.xlsx', data)
    assert len(records) == 1
    assert records[0]['location']['sheet'] == 'G60_G68'
    assert records[0]['metadata']['record_type'] == 'sales_aggregate'
    assert records[0]['metadata']['vehicle_scope'] == ['G60', 'G68']
    assert records[0]['metadata']['columns']['volume_2030'] == 800
    assert records[0]['observed_at'] is None


def test_explicit_other_scope_in_filename_is_filtered():
    assert parse_file('F70_notes.txt', b'Option descriptions') == []


def test_csv_delimiter_bom_multiline_and_scope():
    text = '\ufeffID;Country;Vehicle;Customer Feedback;Date\r\nx;USA;G60;"Slow charger\nNeeds attention";2025-03-01\r\ny;GB;G60;Other;2025-04-02\r\n'
    result = parse_file('feedback.csv', text.encode())
    assert len(result) == 1
    assert result[0]['content'] == 'Slow charger\nNeeds attention'
    assert result[0]['location']['row'] == 2
    assert result[0]['location']['line_end'] == 3
    assert result[0]['observed_at'] == '2025-03-01'


def test_csv_duplicate_headers_preserve_all_values():
    records = parse_file('records.csv', b'Customer Feedback,Category,Category\nGood seat,Seat,Comfort\n')
    assert records[0]['metadata']['columns']['Category (2)'] == 'Comfort'


def test_json_preserves_raw_ambiguous_date_and_structured_context():
    data = json.dumps({'records': [{'content': 'Comparison data', 'vehicle': 'G60', 'market': 'USA', 'date': '03/04/2025', 'metrics': {'range': 300}}]}).encode()
    record = parse_file('records.json', data)[0]
    assert record['content'] == 'Comparison data'
    assert record['observed_at'] is None
    assert record['metadata']['date_status'] == 'unparsed'
    assert record['metadata']['date_original'] == '03/04/2025'
    assert record['metadata']['columns']['metrics'] == {'range': 300}
    assert record['location'] == {'record': 1, 'json_pointer': '/records/0'}


def test_json_iso_timestamp_and_market_normalization():
    result = parse_file('records.json', b'{"feedback":"Quiet cabin","market":"United States","observed_at":"2025-05-01T12:10:00Z"}')
    assert result[0]['observed_at'] == '2025-05-01T12:10:00+00:00'
    assert result[0]['market'] == 'US'


def test_html_omits_scripts_and_styles_and_decodes_entities():
    html = '<html><head><style>hidden</style><script>bad()</script></head><body><h1>Range &amp; charging</h1><p>First <b>test</b>.</p><p>Next.</p></body></html>'
    assert parse_html(html) == 'Range & charging\nFirst test.\nNext.'
    result = parse_file('article.html', html.encode())
    assert result[0]['metadata']['record_type'] == 'document_context'
    assert result[0]['metadata']['scope_basis'] == {'vehicle': 'requested', 'market': 'requested'}


def test_utf16_text_keeps_line_location():
    result = parse_file('note.txt', 'Line one\nLine two'.encode('utf-16'))
    assert result[0]['location'] == {'line_start': 1, 'line_end': 2}
    assert result[0]['content'] == 'Line one\nLine two'


def test_pdf_page_locations_and_password_free_aes():
    result = parse_file('G60_options.PDF', pdf_bytes(['First page', 'Second page'], password=''))
    assert [record['content'] for record in result] == ['First page', 'Second page']
    assert [record['location']['page'] for record in result] == [1, 2]
    assert result[0]['metadata']['record_type'] == 'document_context'
    assert result[0]['metadata']['scope_basis']['market'] == 'requested'


def test_pdf_password_is_reported():
    with pytest.raises(ValueError, match='password'):
        parse_file('document.pdf', pdf_bytes(['Text'], password='secret'))


@pytest.mark.parametrize(('filename', 'data'), [
    ('blank.txt', b''), ('blank.txt', b' \n '), ('binary.txt', b'\x00abc'),
    ('invalid.txt', b'\xffabc'), ('old.xls', b'bytes'), ('bad.xlsx', b'not a zip'),
    ('bad.pdf', b'not a PDF'), ('empty.csv', b'feedback,vehicle\n'),
    ('ragged.csv', b'feedback,vehicle\nx,G60,extra\n'),
    ('bad.json', b'{'), ('bad.json', b'null'), ('bad.json', b'[1]'),
    ('empty.json', b'[]'), ('invalid.json', b'{"content":"x", "value":NaN}'),
])
def test_invalid_empty_and_unsupported_inputs(filename, data):
    with pytest.raises(ValueError):
        parse_file(filename, data)


def test_xlsx_inflated_archive_bound(monkeypatch):
    monkeypatch.setattr(importers, 'MAX_XLSX_UNCOMPRESSED', 100)
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('large.xml', ' ' * 101)
    with pytest.raises(ValueError, match='decompression'):
        parse_file('large.xlsx', output.getvalue())


def test_xlsx_declared_dimensions_bound(monkeypatch):
    data = workbook_bytes({'Sheet': [['Customer Feedback'], ['Record 1'], ['Record 2']]})
    monkeypatch.setattr(importers, 'MAX_ROWS', 2)
    with pytest.raises(ValueError, match='dimensions'):
        parse_file('large.xlsx', data)


def test_text_and_record_limits(monkeypatch):
    monkeypatch.setattr(importers, 'MAX_TEXT_CHARS', 3)
    with pytest.raises(ValueError, match='limits'):
        parse_file('note.txt', b'long text')


def test_single_vehicle_study_matrix_is_aggregate():
    data = workbook_bytes({'US_2025': [['Ride comfort', 'G60'], ['Mean', 8.1]]})
    records = parse_file('study.xlsx', data)
    assert records[0]['metadata']['record_type'] == 'study_aggregate'
    assert records[0]['metadata']['value'] == 8.1


def test_html_keeps_table_cells_separate():
    assert parse_html('<table><tr><td>Range</td><td>300 km</td></tr></table>') == 'Range 300 km'


@pytest.mark.parametrize('feedback', ['   ', 1, {'summary': 'metadata only'}])
def test_only_nonblank_feedback_text_is_customer_testimony(feedback):
    record = parse_file('records.json', json.dumps({'feedback': feedback, 'topic': 'Charging'}).encode())[0]
    assert record['metadata']['record_type'] == 'context'
    assert record['metadata']['columns']['feedback'] == feedback


def test_blank_feedback_uses_available_context_text():
    record = parse_file('records.json', b'{"feedback":"   ","content":"Aggregate summary"}')[0]
    assert record['content'] == 'Aggregate summary'
    assert record['metadata']['record_type'] == 'context'


def test_customer_content_uses_the_actual_testimony_field():
    record = parse_file('records.json', b'{"content":"Analysis summary","comment":"Comfortable seats","volume_2025":8}')[0]
    assert record['content'] == 'Comfortable seats'
    assert record['metadata']['record_type'] == 'customer_feedback'


def test_numeric_feedback_does_not_hide_a_textual_review():
    record = parse_file('records.json', b'{"feedback":3,"review":"Fast charging"}')[0]
    assert record['content'] == 'Fast charging'
    assert record['metadata']['record_type'] == 'customer_feedback'


def test_vehicle_scope_comes_from_filename_instead_of_parent_directory():
    assert parse_file('/G60/files/G70_notes.txt', b'Other car') == []


@pytest.mark.parametrize(('filename', 'vehicle', 'market'), [
    (None, 'G60', 'US'), ('records.txt', None, 'US'), ('records.txt', 'G60', None),
])
def test_invalid_scope_arguments_raise_a_validation_error(filename, vehicle, market):
    with pytest.raises(ValueError, match='Filename, vehicle and market'):
        parse_file(filename, b'Text', vehicle, market)


@pytest.mark.parametrize(('data', 'pointer'), [
    (b'{"content":"Root object"}', ''),
    (b'[{"content":"Array item"}]', '/0'),
    (b'{"records":[{"content":"Wrapped item"}]}', '/records/0'),
])
def test_json_locations_identify_the_actual_object(data, pointer):
    assert parse_file('records.json', data)[0]['location'] == {'record': 1, 'json_pointer': pointer}


def test_duplicate_json_keys_are_rejected_without_losing_source_values():
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        parse_file('records.json', b'{"feedback":"First", "feedback":"Second"}')


def test_json_metadata_keeps_original_keys():
    record = parse_file('records.json', b'{"content":"Text","measurements":{" range ":300}}')[0]
    assert record['metadata']['columns']['measurements'] == {' range ': 300}


def test_csv_total_cells_are_bounded(monkeypatch):
    monkeypatch.setattr(importers, 'MAX_CELLS', 5)
    with pytest.raises(ValueError, match='cell limits'):
        parse_file('records.csv', b'feedback,vehicle\nGood,G60\nQuiet,G60\n')


def test_study_record_budget_stops_expansion_before_later_rows(monkeypatch):
    monkeypatch.setattr(importers, 'MAX_RECORDS', 1)
    data = workbook_bytes({'US_2025': [
        ['Charging', 'G60', 'G70'], ['Mean', 1, 2], ['Bad later row', 3, 4],
    ]})
    original = importers._base_record
    calls = []

    def counted_record(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(importers, '_base_record', counted_record)
    with pytest.raises(ValueError, match='record, extracted text or metadata limits'):
        parse_file('studies.xlsx', data)
    assert len(calls) == 2  # Stop on the first excess record rather than build every row.


def test_output_metadata_budget_counts_repeated_source_columns(monkeypatch):
    monkeypatch.setattr(importers, 'MAX_METADATA_CHARS', 100)
    with pytest.raises(ValueError, match='metadata limits'):
        parse_file('records.json', b'{"content":"Small text","extra":"' + b'x' * 100 + b'"}')


def test_pdf_decompression_budget_is_restored_after_rejection(monkeypatch):
    from pypdf import get_configuration

    writer = PdfWriter()
    writer.append(io.BytesIO(pdf_bytes(['x' * 200])))
    writer.pages[0].compress_content_streams()
    output = io.BytesIO()
    writer.write(output)
    before = get_configuration()
    monkeypatch.setattr(importers, 'MAX_PDF_STREAM_BYTES', 128)
    with pytest.raises(ValueError, match='LimitReachedError'):
        parse_file('compressed.pdf', output.getvalue())
    assert get_configuration() == before


def test_file_scopes_list_every_declared_vehicle_and_market():
    feedback = workbook_bytes({'Feedback_Explorer': [
        ['ID', 'Country', 'Derivate (e-code)', 'Customer Feedback'],
        ['1', 'US', 'G60', 'Simulated A'], ['2', 'KR', 'G60', 'Simulated B'], ['3', 'KR', 'G60', 'Simulated C']]})
    assert file_scopes('G60_feedback.xlsx', feedback) == [
        {'vehicle': 'G60', 'market': 'KR', 'records': 2}, {'vehicle': 'G60', 'market': 'US', 'records': 1}]
    sales = workbook_bytes({'G60_G68': [['market', 'market_code', 'volume_2025'], ['Europe', 'EU', 5]]})
    assert file_scopes('sales.xlsx', sales) == [
        {'vehicle': 'G60', 'market': 'EU', 'records': 1}, {'vehicle': 'G68', 'market': 'EU', 'records': 1}]
    assert file_scopes('G70_options.pdf', pdf_bytes(['Page'])) == [{'vehicle': 'G70', 'market': None, 'records': 1}]
    assert file_scopes('report.txt', b'Simulated report') == [{'vehicle': None, 'market': None, 'records': 1}]


def test_parse_scopes_matches_parse_file_for_each_scope():
    data = workbook_bytes({'US_2025': [['Charging', None, 'BMW 5 Series G60', 'BMW 7 Series G70'], ['Mean', None, 7, 8]],
                           'Feedback': [['Country', 'Vehicle', 'Customer Feedback'], ['US', 'G60', 'Simulated'],
                                        ['GB', 'G60', 'Simulated GB']]})
    scopes = [('G60', 'US'), ('g70', 'usa'), ('G60', 'GB'), ('F70', 'US')]
    parsed = parse_scopes('studies.xlsx', data, scopes)
    assert set(parsed) == {('G60', 'US'), ('G70', 'US'), ('G60', 'GB'), ('F70', 'US')}
    for (vehicle, market), records in parsed.items():
        assert records == parse_file('studies.xlsx', data, vehicle, market)
    assert parsed['F70', 'US'] == []
    document = parse_scopes('report.txt', b'Simulated', [('G60', 'US'), ('G70', 'CN')])
    assert [r['market'] for r in document['G70', 'CN']] == ['CN']
    document['G70', 'CN'][0]['metadata']['changed'] = True  # copies: one scope never mutates another
    assert 'changed' not in document['G60', 'US'][0]['metadata']
