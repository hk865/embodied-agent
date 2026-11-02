"""Download selected public arXiv papers and record exact source versions.

This script only writes inside this research directory. It never installs or
executes downloaded code. PDFs are checked with Poppler; no checksums are used.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
from datetime import date
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
items = json.loads((ROOT / 'sources/selection.json').read_text())
session = requests.Session()
session.headers['User-Agent'] = 'LocalResearchLibrary/1.0 (public paper archiving)'

for item in items:
    if len(sys.argv) > 1 and item['slug'] not in sys.argv[1:]:
        continue
    record_path = ROOT / 'sources' / (item['slug'] + '.json')
    existing = json.loads(record_path.read_text()) if record_path.exists() else {}
    existing_pdf = ROOT / 'papers' / existing.get('filename', '__missing__')
    if existing.get('pdf_valid') and existing_pdf.is_file() and existing_pdf.stat().st_size == existing.get('size_bytes'):
        print(item['slug'], 'already downloaded', flush=True)
        continue
    rec = dict(item, checked_at=date.today().isoformat(), abstract_url=f"https://arxiv.org/abs/{item['id']}")
    try:
        if item.get('pinned_version'):
            rec['abstract_url'] += item['pinned_version']
        response = session.get(rec['abstract_url'], timeout=40)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        metas = {}
        for tag in soup.find_all('meta'):
            name = tag.get('name', '')
            if name.startswith('citation_'):
                metas.setdefault(name, []).append(tag.get('content', ''))
        rec['metadata'] = metas
        rec['title'] = metas['citation_title'][0]
        rec['authors'] = metas.get('citation_author', [])
        history = soup.select_one('.submission-history')
        rec['submission_history'] = history.get_text(' ', strip=True) if history else ''
        versions = re.findall(r'\[v(\d+)\]', rec['submission_history'])
        rec['version'] = item.get('pinned_version') or ('v' + str(max(map(int, versions))) if versions else '')
        if not rec['version']:
            raise ValueError('No arXiv version found')
        abstract = soup.select_one('blockquote.abstract')
        rec['abstract'] = abstract.get_text(' ', strip=True) if abstract else ''
        rec['official_links'] = list(dict.fromkeys(a['href'] for a in (abstract.find_all('a', href=True) if abstract else []) if a['href'].startswith('http')))
        rec['pdf_url'] = f"https://arxiv.org/pdf/{item['id']}{rec['version']}"
        rec['filename'] = f"{item['id']}{rec['version']}_{item['slug']}.pdf"
        r = session.get(rec['pdf_url'], timeout=80)
        r.raise_for_status()
        rec['content_type'] = r.headers.get('Content-Type')
        rec['resolved_pdf_url'] = r.url
        if not r.content.startswith(b'%PDF-'):
            raise ValueError('Response does not start with PDF magic bytes')
        pdf = ROOT / 'papers' / rec['filename']
        pdf.write_bytes(r.content)
        rec['size_bytes'] = pdf.stat().st_size
        info = subprocess.run(['pdfinfo', str(pdf)], check=True, text=True, capture_output=True).stdout
        rec['pdfinfo'] = info
        text_file = ROOT / 'sources' / (item['slug'] + '.txt')
        subprocess.run(['pdftotext', '-layout', str(pdf), str(text_file)], check=True, capture_output=True)
        body = text_file.read_text(errors='replace')
        if len(body.strip()) < 300:
            raise ValueError('PDF text not readable')
        rec['first_page_excerpt'] = body.split('\f')[0][:5000]
        rec['pdf_valid'] = True
        print(item['slug'], rec['title'], rec['version'], len(r.content), 'bytes', flush=True)
    except Exception as exc:
        rec['pdf_valid'] = False
        rec['error'] = str(exc)
        print(item['slug'], 'FAILED', str(exc), flush=True)
    record_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
