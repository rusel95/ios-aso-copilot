#!/usr/bin/env python3
"""Validate model-reviewed Apple Ads candidates; local CSV exports only, no network or writes to Ads.

    ads_keywords.py --input candidates.csv --output reviewed --brand compresso --brand 'media cleaner'
    ads_keywords.py --self-check

The model supplies complete phrases, product paths and a second-pass review. Python checks the
contract, preserves relevant protected seeds and makes selection repeatable; it cannot judge fluency.
"""
import argparse
import csv
import json
import tempfile
import unicodedata
from pathlib import Path

from ledger import brand_hit

FIELDS = ['text', 'language', 'intent', 'source', 'evidence', 'translation_uk',
          'classification', 'product_path', 'review_reason', 'protected']
EVIDENCE = {'seed', 'suggestion', 'keyword_delivery', 'search_term', 'model'}


def norm(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def select(rows, brands=(), limit=5000):
    if not 1 <= limit <= 5000:
        raise ValueError('limit must be 1..5000; it is a ceiling, not a target')
    ready, rejected = [], []
    for original in rows:
        row = {k: str(original.get(k) or '').strip() for k in FIELDS}
        # Casefold is a comparison key (ß -> ss), not the spelling to send to Apple.
        row['text'] = ' '.join(unicodedata.normalize('NFC', row['text']).lower().split())
        reason = ''
        if any(not row[k] for k in FIELDS):
            reason = 'missing_required_field'
        elif row['protected'] not in {'true', 'false'}:
            reason = 'invalid_protected_flag'
        elif row['evidence'] not in EVIDENCE:
            reason = 'invalid_evidence_kind'
        elif row['classification'] not in {'core', 'adjacent', 'reject'}:
            reason = 'invalid_classification'
        elif row['classification'] == 'reject':
            reason = 'semantic_reject: ' + row['review_reason']
        elif len(row['text']) > 80 or any(unicodedata.category(c)[0] == 'C' for c in row['text']):
            reason = 'text_limit_or_control_character'
        elif any(brand_hit(norm(b), row['text']) for b in brands):
            reason = 'brand_token'
        if reason:
            if row['protected'] == 'true':
                raise ValueError(f"Protected seed failed review: {row['text']}: {reason}")
            rejected.append(dict(row, reason=reason))
        else:
            ready.append(row)
    # Evidence is a type, not a score. Never infer demand from hints or model output.
    rank = {'search_term': 0, 'keyword_delivery': 1, 'seed': 2, 'suggestion': 3, 'model': 4}
    ready.sort(key=lambda r: (r['protected'] != 'true', rank[r['evidence']], norm(r['text']),
                              tuple(r[k] for k in FIELDS)))
    accepted, seen = [], set()
    for row in ready:
        key = norm(row['text'])
        if key in seen:
            rejected.append(dict(row, reason='exact_normalized_duplicate'))
        else:
            seen.add(key)
            accepted.append(row)
    protected = sum(r['protected'] == 'true' for r in accepted)
    if protected > limit:
        raise ValueError(f'{protected} protected seeds exceed limit {limit}; split the group')
    rejected.extend(dict(r, reason='capacity_deferred') for r in accepted[limit:])
    # Word-order families are labels for review; they are not independent demand or auto-duplicates.
    accepted = [dict(r, word_order_family=' '.join(sorted(r['text'].split()))) for r in accepted[:limit]]
    rejected.sort(key=lambda r: (r['text'], r['reason'], tuple(r[k] for k in FIELDS)))
    return accepted, rejected


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def export(source, output, brands=(), limit=5000):
    with source.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if not set(FIELDS) <= set(reader.fieldnames or []):
            raise ValueError('CSV header must include: ' + ','.join(FIELDS))
        accepted, rejected = select(list(reader), brands, limit)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / 'accepted.csv', accepted, FIELDS + ['word_order_family'])
    write_csv(output / 'rejected.csv', rejected, FIELDS + ['reason'])
    (output / 'keywords.txt').write_text(''.join(r['text'] + '\n' for r in accepted), encoding='utf-8')
    summary = dict(accepted=len(accepted), rejected=len(rejected),
                   protected=sum(r['protected'] == 'true' for r in accepted),
                   capacity=limit, network=False, semantic_review='supplied_by_model_not_verified_by_python')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def self_check():
    def row(text, protected='false', **kw):
        return dict(zip(FIELDS, [text, 'en', 'video', 'model:check', 'model', 'Стиснути відео',
                                'core', 'Photos compression', 'natural phrase; one supported task', protected]), **kw)
    rows = [row('  VIDEÓ   compressor '), row('videó compressor'), row('compresso video'),
            row('video compressor', 'true'), row('compress video'), row('video compress')]
    accepted, rejected = select(rows, ['compresso'], 2)
    assert accepted[0]['text'] == 'video compressor' and len(accepted) == 2
    assert {r['reason'] for r in rejected} >= {'exact_normalized_duplicate', 'brand_token', 'capacity_deferred'}
    assert select(rows[::-1], ['compresso'], 2) == (accepted, rejected)
    family, _ = select([row('compress video'), row('video compress')])
    assert len(family) == 2 and family[0]['word_order_family'] == family[1]['word_order_family']
    spelling, duplicates = select([row('Straße', 'true'), row('STRASSE')])
    assert spelling[0]['text'] == 'straße' and len(spelling) == len(duplicates) == 1
    try:
        select([row('compresso', 'true')], ['compresso'])
    except ValueError:
        pass
    else:
        raise AssertionError('a rejected protected seed must stop the export')
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        write_csv(p / 'in.csv', rows, FIELDS)
        assert export(p / 'in.csv', p / 'out', ['compresso'], 2)['accepted'] == 2
        assert (p / 'out' / 'keywords.txt').read_text().splitlines()[0] == 'video compressor'
    print('OK: normalization, compressor vs brand, deterministic cap, protected seeds, word-order labels, CSV export')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--brand', action='append', default=[])
    parser.add_argument('--limit', type=int, default=5000)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
    elif args.input and args.output:
        print(json.dumps(export(args.input, args.output, args.brand, args.limit)))
    else:
        parser.error('supply --input and --output, or --self-check')


if __name__ == '__main__':
    main()
