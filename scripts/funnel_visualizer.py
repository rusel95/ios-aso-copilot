#!/usr/bin/env python3
"""Render observed metrics. Missing data stays missing; counts are not a cohort funnel."""
import argparse
import csv
import json
import math
from pathlib import Path
import tempfile

FIELDS = {
    'impressions': 'Impressions (unit must be checked in source)',
    'product_page_views': 'Product page views',
    'downloads': 'Downloads (first-time/total: check source)',
    'trial_starts': 'Trial starts',
    'paid_subscribers': 'Paying subscribers',
}


def number(value, *, count=False):
    if value is None or str(value).strip() == '' or str(value).startswith('absent:'):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0 or (count and not result.is_integer()):
        raise ValueError(f'Invalid number: {value!r}')
    return int(result) if count else result


def select_row(path, week=None, segment=None, market=None):
    if not path.exists():
        return None
    with path.open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    for key, value in (('week_start', week), ('segment', segment), ('market', market)):
        if value is not None:
            rows = [r for r in rows if r.get(key) == value]
    if not rows:
        return None
    latest = max(r.get('week_start', '') for r in rows)
    rows = [r for r in rows if r.get('week_start', '') == latest]
    if len(rows) != 1:
        raise ValueError('Ambiguous weekly rows. Select --week, --segment and --market; reconcile duplicate records. Do not sum unique devices across segments.')
    return rows[0]


def observation(row, period):
    row = row or {}
    return {
        'period': period,
        'segment': row.get('segment'),
        'market': row.get('market'),
        'source': row.get('source') or 'absent:no source recorded',
        'recorded': row.get('recorded'),
        **{key: number(row.get(key), count=True) for key in FIELDS},
        # Legacy counts do not identify the denominator. Preserve only an explicitly reported rate.
        'reported_cvr_pct': number(row.get('cvr_pct')),
        'health': 'not_assessed',
        'note': row.get('note', ''),
    }


def render(data):
    lines = [f"# Observed marketing metrics - {data['period']}", '',
             f"Source: {data['source']}; segment: {data['segment'] or 'unspecified'}; market: {data['market'] or 'unspecified'}", '',
             '| Metric | Observed value |', '|---|---:|']
    for key, label in FIELDS.items():
        value = data[key]
        lines.append(f"| {label} | {value if value is not None else 'absent'} |")
    cvr = data['reported_cvr_pct']
    lines.append(f"| Reported conversion rate (verify source definition) | {str(cvr) + '%' if cvr is not None else 'absent'} |")
    lines += ['', 'Health: not assessed. No matched benchmark or experiment evidence was supplied.',
              'Downloads may happen without opening the product page. Trials are not payments. Same-week totals are not a joined cohort.',
              'ASC Search can include Apple Ads. Source shares, revenue and bank payouts are not inferred from these counts.']
    if data['note']:
        lines += ['', data['note']]
    return '\n'.join(lines)


def self_check():
    empty = observation(None, 'empty')
    assert all(empty[k] is None for k in FIELDS)
    assert empty['health'] == 'not_assessed'
    trial = observation({'trial_starts': '3', 'downloads': '0'}, 'test')
    assert trial['paid_subscribers'] is None and trial['downloads'] == 0
    assert '546' not in render(empty) and 'net_cash' not in empty
    for bad in ('nan', 'inf', '-1', '0.5'):
        try:
            number(bad, count=True)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'weekly.csv'
        path.write_text('week_start,segment,downloads\n', encoding='utf-8')
        assert select_row(path) is None
        path.write_text('week_start,segment,downloads\n2026-09-07,search,0\n2026-09-07,browse,2\n', encoding='utf-8')
        try:
            select_row(path)
        except ValueError:
            pass
        else:
            raise AssertionError('Mixed segments must not silently select the last row')
        assert select_row(path, segment='search')['downloads'] == '0'
    print('OK: absent data, zero, unpaid trials, invalid numbers and mixed segments')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', default='marketing')
    for flag in ('impressions', 'views', 'downloads', 'trials', 'paid'):
        parser.add_argument('--' + flag, help='Observed count, never estimated')
    for flag in ('week', 'segment', 'market', 'period', 'output'):
        parser.add_argument('--' + flag)
    parser.add_argument('--format', choices=['pyramid', 'markdown', 'json'], default='markdown',
                        help='pyramid is a compatibility alias for the non-sequential metrics table')
    parser.add_argument('--price', help='Deprecated: price alone cannot establish proceeds')
    parser.add_argument('--no-cash', action='store_true', help='Compatibility flag; cash is never inferred')
    parser.add_argument('--no-sources', action='store_true', help='Compatibility flag; source shares are never inferred')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if args.price is not None:
        parser.error('--price cannot calculate actual revenue; use economics.py for an explicitly labelled scenario')
    try:
        flags = (args.impressions, args.views, args.downloads, args.trials, args.paid)
        if any(v is not None for v in flags):
            row = dict(zip(FIELDS, flags))
            row.update(source='user-supplied CLI counts', segment=args.segment, market=args.market)
        else:
            row = select_row(Path(args.store) / 'metrics/weekly.csv', args.week, args.segment, args.market)
        period = args.period or ((row or {}).get('week_start')) or 'No matching weekly record'
        data = observation(row, period)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    result = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) if args.format == 'json' else render(data)
    if args.output:
        Path(args.output).write_text(result + '\n', encoding='utf-8')
    else:
        print(result)


if __name__ == '__main__':
    main()
