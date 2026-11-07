"""Deterministic extraction. Every candidate retains an exact source span.

This deliberately favors abstention over inventing a date, currency, or term.
It does not interpret legal authority or use a remote language model.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

MAX_FILE = 12 * 1024 * 1024
MAX_TEXT = 1_500_000
SUPPORTED = {'.txt', '.md', '.csv', '.pdf', '.docx'}


class InputError(ValueError):
    pass


def read_document(filename: str, content: bytes) -> tuple[str, list[str]]:
    if not content or len(content) > MAX_FILE:
        raise InputError('Choose a nonempty file smaller than 12 MB.')
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED:
        raise InputError('Supported files: PDF, DOCX, TXT, Markdown, and CSV.')
    warnings = []
    if extension == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise InputError('PDF support needs pypdf. Run: python3 -m pip install -r requirements.txt') from exc
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted and not reader.decrypt(''):
                raise InputError('This PDF is password protected. Import an unlocked copy.')
            if len(reader.pages) > 250:
                raise InputError('Split this PDF into files of 250 pages or fewer.')
            pages = []
            total = 0
            for page in reader.pages:
                value = page.extract_text() or ''
                total += len(value)
                if total > MAX_TEXT:
                    raise InputError('This document contains too much text. Split it into smaller files.')
                pages.append(value)
            text = '\n\f\n'.join(pages)
            if any(not page.strip() for page in pages):
                warnings.append('Some pages contain no selectable text. Scanned pages need OCR before import.')
        except InputError:
            raise
        except Exception as exc:
            raise InputError('This PDF could not be read. Try exporting a fresh copy.') from exc
    elif extension == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > 20 * 1024 * 1024:
                    raise InputError('The text inside this DOCX is too large.')
                xml = archive.read(info)
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                    raise InputError('This DOCX contains unsupported XML declarations.')
                root = ElementTree.fromstring(xml)
                ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                text = '\n'.join(''.join(node.text or '' for node in paragraph.iter(ns + 't')) for paragraph in root.iter(ns + 'p'))
                warnings.append('DOCX citations refer to extracted paragraphs, not printed page numbers.')
        except InputError:
            raise
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise InputError('This DOCX could not be read.') from exc
    else:
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise InputError('Save this text file with UTF-8 encoding and try again.') from exc
        if extension == '.csv':
            try:
                list(csv.reader(io.StringIO(text), strict=True))
            except csv.Error as exc:
                raise InputError('This CSV is malformed.') from exc
            warnings.append('CSV text is searchable; structured extraction works best with labeled terms in each row.')
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')
    if len(text) > MAX_TEXT:
        raise InputError('This document contains too much text. Split it into smaller files.')
    if not text.strip():
        raise InputError('No readable text was found. Scanned documents need OCR before import.')
    if re.search(r'\b(?:0?[1-9]|1[0-2])[/.-](?:0?[1-9]|1[0-2])[/.-]\d{4}\b', text):
        warnings.append('Ambiguous numeric dates were left uninterpreted. Use YYYY-MM-DD or a written month.')
    return text, warnings


def passages(text: str) -> list[dict]:
    """Split into bounded, exact slices; preserve PDF page and line locations."""
    result = []
    page, line = 1, 0
    for match in re.finditer(r'[^\n\f]+|\f', text):
        if match.group() == '\f':
            page += 1
            line = 0
            continue
        line += 1
        raw = match.group()
        if not raw.strip():
            continue
        offset = match.start()
        # A sentence boundary is punctuation followed by space and a capital.
        # Avoid splitting decimal amounts or abbreviated names at every period.
        for sentence in re.finditer(r'.+?(?:[.!?](?=\s+[A-Z])|$)', raw):
            start = offset + sentence.start()
            value = sentence.group()
            while value:
                cut = len(value) if len(value) <= 1200 else (value.rfind(' ', 0, 1200) or 1200)
                if cut <= 0:
                    cut = 1200
                piece = value[:cut]
                left = len(piece) - len(piece.lstrip())
                end = len(piece.rstrip())
                if end > left:
                    result.append({'ordinal': len(result), 'start': start + left, 'end': start + end, 'text': piece.strip(), 'page': page, 'line': line})
                start += cut
                value = value[cut:]
    return result


MONTHS = {name: i for i, names in enumerate([
    ('jan', 'january'), ('feb', 'february'), ('mar', 'march'), ('apr', 'april'),
    ('may',), ('jun', 'june'), ('jul', 'july'), ('aug', 'august'),
    ('sep', 'sept', 'september'), ('oct', 'october'), ('nov', 'november'), ('dec', 'december'),
], 1) for name in names}
MONTH_RE = '|'.join(sorted(MONTHS, key=len, reverse=True))
DATE_RE = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:' + MONTH_RE + r')\.?\s+\d{4}|(?:' + MONTH_RE + r')\.?\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})\b', re.I)
MONEY_RE = re.compile(r'(?<!\w)(?P<currency>USD|EUR|GBP|NGN|CAD|AUD|KES|GHS|INR|ZAR|[$£€₦])\s*(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?!\d|[.,]\d)', re.I)


def parse_date(value: str) -> str | None:
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat()
        clean = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', value.lower()).replace(',', '').replace('.', '')
        parts = clean.split()
        if parts[0].isdigit():
            day, month, year = int(parts[0]), MONTHS[parts[1]], int(parts[2])
        else:
            day, month, year = int(parts[1]), MONTHS[parts[0]], int(parts[2])
        return date(year, month, day).isoformat()
    except (ValueError, KeyError, IndexError):
        return None


DATE_CONCEPTS = [
    ('effective_date', 'Effective date', r'\beffective\b|\bcommences?\b|\bstarts? on\b'),
    ('cancellation_deadline', 'Cancellation deadline', r'\bcancel(?:lation)?\b|\bnotice (?:by|before|deadline)\b'),
    ('due_date', 'Payment due', r'\bdue\b|\bpay(?:ment)? (?:by|before|no later)\b|\bmust be paid\b'),
    ('renewal_date', 'Renewal date', r'\brenew(?:al|s)?\b'),
    ('expiry_date', 'Expiry date', r'\bexpir(?:y|es|ation)\b|\bends? on\b|\bvalid until\b'),
    ('delivery_date', 'Delivery date', r'\bdeliver(?:y|ed)?\b|\bsubmit\b|\bdeadline\b'),
]
MONEY_CONCEPTS = [
    ('monthly_rent', 'Monthly rent', r'\b(?:monthly\s+)?rent\b'),
    ('deposit', 'Deposit', r'\bdeposit\b'),
    ('annual_premium', 'Annual premium', r'\b(?:annual\s+)?premium\b'),
    ('coverage_limit', 'Coverage limit', r'\bcoverage\b|\binsured\b'),
    ('invoice_total', 'Invoice total', r'\binvoice total\b|\btotal (?:amount|due)\b|\bamount due\b'),
    ('monthly_fee', 'Monthly fee', r'\bmonthly (?:fee|cost|price|subscription)\b'),
    ('salary', 'Salary', r'\bsalary\b'),
    ('payment_amount', 'Payment amount', r'\bpayment\b|\bpay\b'),
]


def nearest_concept(text: str, start: int, end: int, concepts: list) -> tuple | None:
    candidates = []
    for priority, (key, label, pattern) in enumerate(concepts):
        for match in re.finditer(pattern, text, re.I):
            # Prefer a label immediately before a value, but accept "date: due".
            distance = start - match.end() if match.end() <= start else match.start() - end + 18
            if -18 <= distance < 95:
                candidates.append((max(0, distance), priority, key, label))
    if not candidates:
        return None
    _, _, key, label = min(candidates)
    return key, label


def extract(text: str) -> tuple[list[dict], list[dict]]:
    chunks = passages(text)
    facts = []
    seen = set()
    for chunk in chunks:
        value = chunk['text']

        def add(key, label, normalized, display, kind, start, end, unit=''):
            identity = (chunk['ordinal'], key, normalized, unit)
            if identity in seen:
                return
            seen.add(identity)
            facts.append({'key': key, 'label': label, 'value': normalized, 'display': display, 'kind': kind, 'unit': unit,
                          'chunk': chunk['ordinal'], 'start': chunk['start'] + start, 'end': chunk['start'] + end,
                          'quote': value, 'status': 'suggested'})

        for match in DATE_RE.finditer(value):
            normalized = parse_date(match.group())
            concept = nearest_concept(value, match.start(), match.end(), DATE_CONCEPTS)
            if normalized and concept:
                add(*concept, normalized, normalized, 'date', match.start(), match.end())
        for match in MONEY_RE.finditer(value):
            concept = nearest_concept(value, match.start(), match.end(), MONEY_CONCEPTS)
            if not concept:
                continue
            try:
                normalized = str(Decimal(match.group('amount').replace(',', '')).quantize(Decimal('.01')))
            except InvalidOperation:
                continue
            unit = {'£': 'GBP', '€': 'EUR', '₦': 'NGN'}.get(match.group('currency'), match.group('currency').upper())
            add(*concept, normalized, f'{unit} {Decimal(normalized):,.2f}', 'money', match.start(), match.end(), unit)
        for match in re.finditer(r'\b(?:(?:notice (?:period|of)\s*:?\s*)(\d{1,3})\s+days?|(\d{1,3})\s+days?[’\x27]?\s+(?:written\s+)?notice)\b', value, re.I):
            number = match.group(1) or match.group(2)
            add('notice_days', 'Notice period', str(int(number)), f'{int(number)} days', 'duration', match.start(), match.end(), 'days')
    return chunks, facts
