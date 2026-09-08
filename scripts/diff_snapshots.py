#!/usr/bin/env python3
"""Compare exact query pairs with matching provenance. Markdown cannot prove query coverage."""
import argparse
import json
from pathlib import Path


def load_data(path):
    if Path(path).suffix != '.json':
        raise ValueError('Use JSON snapshots. Markdown rank-only tables cannot distinguish unqueried from absent.')
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Expected country -> query rows')
    return data


def compare(before, after):
    result = []
    for country in sorted(set(before) | set(after)):
        maps = []
        for data in (before, after):
            rows = data.get(country, [])
            mapping = {r['term']: r for r in rows}
            if len(mapping) != len(rows):
                raise ValueError(f'Duplicate queries in {country}')
            maps.append(mapping)
        b, a = maps
        for term in sorted(set(b) | set(a)):
            old, new = b.get(term), a.get(term)
            status, delta = 'unpaired query', None
            if old is not None and new is not None:
                keys = ('source', 'rank_kind', 'bundle_id', 'query_limit')
                if old.get('query_status') != 'ok' or new.get('query_status') != 'ok':
                    status = 'error or legacy provenance missing'
                elif not old.get('observed_at') or not new.get('observed_at'):
                    status = 'observation date missing'
                elif any(old.get(k) is None or old.get(k) != new.get(k) for k in keys):
                    status = 'incomparable provider or method'
                elif old.get('our_rank') is None or new.get('our_rank') is None:
                    status = 'paired presence observation; no numeric delta'
                else:
                    delta = old['our_rank'] - new['our_rank']
                    status = 'paired API position change; causality unproven'
            result.append({'country': country, 'term': term, 'before': (old or {}).get('our_rank'),
                           'after': (new or {}).get('our_rank'), 'delta': delta, 'status': status})
    return result


def self_check():
    r = dict(term='photo', our_rank=12, source='itunes-search-api', rank_kind='api_order_proxy',
             bundle_id='com.test', query_limit=200, query_status='ok', observed_at='2026-09-01')
    after = dict(r, our_rank=8, observed_at='2026-09-08')
    assert compare({'us':[r]}, {'us':[after]})[0]['delta'] == 4
    assert compare({'us':[]}, {'us':[after]})[0]['status'] == 'unpaired query'
    for change in ({'query_status':'error'}, {'source':'another-provider'}, {'observed_at':None}):
        assert compare({'us':[r]}, {'us':[dict(after, **change)]})[0]['delta'] is None
    assert compare({'us':[{'term':'photo','our_rank':12}]}, {'us':[after]})[0]['delta'] is None
    print('OK: exact query basket, method, identity, observation dates and failed requests')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before', nargs='?')
    p.add_argument('after', nargs='?')
    p.add_argument('--self-check', action='store_true')
    args = p.parse_args()
    if args.self_check:
        return self_check()
    if not args.before or not args.after:
        p.error('before and after JSON snapshots required')
    try:
        rows = compare(load_data(args.before), load_data(args.after))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        p.error(str(exc))
    print('# Paired query observations\n\nPositive delta means an earlier API position. It does not measure installs or establish an ASO effect.\n')
    print('| Market | Query | Before | After | Delta | Comparability |\n|---|---|---:|---:|---:|---|')
    for row in rows:
        values = [row[k] for k in ('country','term','before','after','delta','status')]
        print('| ' + ' | '.join(str(x).replace('|', r'\|') if x is not None else 'unknown' for x in values) + ' |')


if __name__ == '__main__':
    main()
