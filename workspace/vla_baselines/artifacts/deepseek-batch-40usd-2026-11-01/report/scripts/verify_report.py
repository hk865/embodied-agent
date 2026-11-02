#!/usr/bin/env python3
"""Offline consistency, PDF geometry and scoped sensitive-value checks."""
import csv
import hashlib
import json
import re
from pathlib import Path
from decimal import Decimal

import pdfplumber
from pypdf import PdfReader

root = Path(__file__).resolve().parents[1]
pdf = root.parents[4] / 'docs/reports/libero-pilot-report.pdf'
stats = json.loads((root / 'data/statistics.json').read_text())
budget = json.loads((root / 'data/budget_analysis.json').read_text())
cases = json.loads((root / 'cases/cases.json').read_text())['cases']
episodes = list(csv.DictReader((root / 'data/episodes.csv').open()))
assert len(episodes) == len({e['cell_id'] for e in episodes}) == 117
assert sum(int(e['transcript_tool_calls']) for e in episodes) == 8313
assert sum(int(e['paired_tool_results']) for e in episodes) == 8312
assert sum(e['outcome'] == 'success' for e in episodes) == 104
assert sum(e['outcome'] == 'failure' for e in episodes) == 12
assert sum(e['outcome'] == 'budget_stopped' for e in episodes) == 1
assert len(cases) == 7 and sum(len(c['steps']) for c in cases) == 52
assert sum(len(c['images']) for c in cases) == 21
assert sum(Decimal(x['accounted_upper_bound_usd']) for x in budget['per_episode']) == Decimal('39.668951088')
pages = []
all_text = ''
with pdfplumber.open(pdf) as doc:
    for i, page in enumerate(doc.pages, 1):
        text = page.extract_text() or ''
        all_text += text + '\n'
        overflow = [c for c in page.chars if c['x0'] < 20 or c['x1'] > page.width - 20
                    or c['top'] < 8 or c['bottom'] > page.height - 8]
        assert not overflow, f'Page {i}: text outside safe page geometry'
        assert '\ufffd' not in text and '\x00' not in text, f'Page {i}: invalid text mapping'
        assert len(text) > 80 or page.images, f'Page {i}: unexpectedly blank'
        pages.append({'page': i, 'text_characters': len(text), 'images': len(page.images),
                      'geometry_overflow_characters': 0})
for term in ('8313', '104', '39.668951', '1883', 'LIBERO', 'budget'):
    assert term in all_text, f'Expected report content missing: {term}'
assert len(PdfReader(pdf).pages) == len(pages)
patterns = [re.compile(r'\bsk-[A-Za-z0-9_-]{16,}'),
            re.compile(r'Bearer\s+[A-Za-z0-9._-]{16,}', re.I)]
scanned = 0
for p in root.rglob('*'):
    if p.is_file() and p.suffix in ('.json', '.csv', '.md', '.py') and 'tmp' not in p.relative_to(root).parts:
        content = p.read_text(errors='replace')
        assert not any(rx.search(content) for rx in patterns), f'Sensitive-value pattern in {p.name}'
        scanned += 1
assert not any(rx.search(all_text) for rx in patterns), 'Sensitive-value pattern in PDF text'
result = {'passed': True, 'episodes': 117, 'tool_calls': 8313, 'paired_tool_results': 8312,
          'cases': 7, 'case_steps': 52, 'case_images': 21, 'pdf_pages': len(pages),
          'pdf_bytes': pdf.stat().st_size, 'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
          'scoped_text_files_scanned': scanned, 'sensitive_value_patterns_found': 0,
          'per_page': pages,
          'visual_review': 'Separate PNG inspection is required; this script does not assert visual layout quality.'}
(root / 'data/validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'per_page'}, ensure_ascii=False))
