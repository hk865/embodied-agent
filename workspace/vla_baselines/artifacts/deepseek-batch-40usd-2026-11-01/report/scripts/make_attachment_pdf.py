#!/usr/bin/env python3
"""Re-encode only simulation images; preserve every page and vector text."""
import hashlib
import json
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

root = Path(__file__).resolve().parents[1]
source = root / 'output/pdf/DeepSeek_RPent_LIBERO_试运行分析报告.pdf'
target = root / 'output/pdf/DeepSeek_RPent_LIBERO_试运行分析报告_附件轻量版.pdf'
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
reader = PdfReader(source)
before_text = [p.extract_text() for p in reader.pages]
before_images = [len(p.images) for p in reader.pages]
writer = PdfWriter(clone_from=reader)
replacements = []
for page_number, page in enumerate(writer.pages, 1):
    for image in page.images:
        im = image.image
        if im.mode == 'RGB' and im.size == (1024, 1024):
            scaled = im.resize((900, 900), Image.Resampling.LANCZOS)
            image.replace(scaled, quality=88, optimize=True, subsampling=0)
            replacements.append({'page': page_number, 'original': [1024, 1024],
                                 'attachment': [900, 900], 'jpeg_quality': 88})
assert len(replacements) == 21
with target.open('wb') as f:
    writer.write(f)
after = PdfReader(target)
assert len(after.pages) == len(reader.pages) == 33
assert [p.extract_text() for p in after.pages] == before_text
assert [len(p.images) for p in after.pages] == before_images
assert all(a.mediabox == b.mediabox for a, b in zip(reader.pages, after.pages))
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
assert target.stat().st_size < 10 * 1024 * 1024
result = {'source': source.name, 'source_bytes': source.stat().st_size,
          'source_sha256': source_sha, 'attachment': target.name,
          'attachment_bytes': target.stat().st_size,
          'attachment_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'pages': len(after.pages), 'identical_page_text': True,
          'same_page_geometry': True, 'same_image_counts': True,
          'vector_text_and_tables_preserved': True,
          'charts_unchanged': 4, 'simulation_image_replacements': replacements,
          'visual_check': 'Pending critical-page rendering review.'}
(root / 'data/attachment_compression.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'simulation_image_replacements'},
                 ensure_ascii=False))
