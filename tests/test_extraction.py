import io
import unittest
import zipfile

from lipso.extract import InputError, extract, parse_date, passages, read_document


class ExtractionTests(unittest.TestCase):
    def test_labeled_money_with_sentence_punctuation(self):
        text = 'Monthly rent: USD 1,850.00.\nDeposit: ₦450,000.\nAnnual premium: EUR 90.'
        _, facts = extract(text)
        self.assertEqual([(f['key'], f['value'], f['unit']) for f in facts], [('monthly_rent', '1850.00', 'USD'), ('deposit', '450000.00', 'NGN'), ('annual_premium', '90.00', 'EUR')])

    def test_currency_symbol_is_not_assumed_us_dollars(self):
        _, facts = extract('Monthly fee: $25.00')
        self.assertEqual(facts[0]['unit'], '$')

    def test_amount_like_an_identifier_not_extracted(self):
        self.assertEqual(extract('Reference 123456.\nAccount USD1234.')[1], [])

    def test_exact_source_spans_with_unicode_and_pages(self):
        text = '  Terms for Élodie\n\n  Monthly rent: NGN 500,000.00.\n\f\nPayment due on 2026-12-31.'
        chunks, facts = extract(text)
        for chunk in chunks:
            self.assertEqual(text[chunk['start']:chunk['end']], chunk['text'])
        for fact in facts:
            chunk = chunks[fact['chunk']]
            self.assertEqual(fact['quote'], text[chunk['start']:chunk['end']])
            self.assertTrue(chunk['start'] <= fact['start'] < fact['end'] <= chunk['end'])
        self.assertEqual(chunks[-1]['page'], 2)

    def test_dates_and_notice_periods(self):
        text = 'Payment due: 14th May 2027.\nRenewal date: June 2, 2027.\n30 days written notice required.\nEffective date: 2026-11-07.'
        _, facts = extract(text)
        self.assertEqual({f['key']: f['value'] for f in facts}, {'due_date': '2027-05-14', 'renewal_date': '2027-06-02', 'notice_days': '30', 'effective_date': '2026-11-07'})

    def test_multiple_labels_on_one_line(self):
        _, facts = extract('Monthly rent: USD 2,000; deposit: USD 4,000.')
        self.assertEqual({f['key']: f['value'] for f in facts}, {'monthly_rent': '2000.00', 'deposit': '4000.00'})

    def test_ambiguous_and_relative_dates_abstain(self):
        text, warnings = read_document('dates.txt', b'Payment due 03/04/2027.\nRenewal date: 30 days after signing.')
        self.assertTrue(warnings)
        self.assertEqual(extract(text)[1], [])

    def test_impossible_date_is_rejected(self):
        self.assertIsNone(parse_date('2027-02-30'))
        self.assertIsNone(parse_date('32 May 2027'))

    def test_empty_and_invalid_imports(self):
        for filename, content in [('x.txt', b''), ('x.exe', b'file'), ('x.txt', b'\xff'), ('x.pdf', b'bad pdf')]:
            with self.subTest(filename=filename, content=content), self.assertRaises(InputError):
                read_document(filename, content)

    def test_docx_preserves_paragraph_order(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Monthly rent: </w:t></w:r><w:r><w:t>USD 100.</w:t></w:r></w:p><w:p><w:r><w:t>Payment due 2027-01-01.</w:t></w:r></w:p></w:body></w:document>')
        text, _ = read_document('lease.docx', output.getvalue())
        self.assertEqual(len(extract(text)[1]), 2)

    def test_blank_pdf_requires_ocr(self):
        from pypdf import PdfWriter
        writer, stream = PdfWriter(), io.BytesIO()
        writer.add_blank_page(200, 200)
        writer.write(stream)
        with self.assertRaisesRegex(InputError, 'OCR'):
            read_document('scan.pdf', stream.getvalue())

    def test_selectable_pdf_text_extracts_findings(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer, output = PdfWriter(), io.BytesIO()
        page = writer.add_blank_page(500, 500)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 50 400 Td (Monthly rent: USD 100.) Tj 0 -20 Td (Payment due 2027-01-01.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(output)
        text, _ = read_document('selectable.pdf', output.getvalue())
        self.assertEqual({f['key'] for f in extract(text)[1]}, {'monthly_rent', 'due_date'})

    def test_long_passages_remain_bounded(self):
        text = ('a' * 2500) + '\n' + ('word ' * 1000)
        chunks = passages(text)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertLessEqual(len(chunk['text']), 1200)
            self.assertEqual(text[chunk['start']:chunk['end']], chunk['text'])
