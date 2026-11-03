#!/usr/bin/env python3
"""Render checkpoint-1 metadata for owner review, without new API calls."""
import argparse
import html
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def safe(value):
    return html.escape(str(value if value is not None else '—')).replace('|', '&#124;').replace('\n', ' ')


def report(snapshot):
    folder = ROOT / 'data' / ('snapshot-' + snapshot)
    data = json.loads((folder / 'seeds.json').read_text())
    counts = json.loads((folder / 'counts.json').read_text())
    records = data['seeds']
    latest_errors = Counter()
    for row in records:
        for provider in ('openalex', 's2'):
            statuses = [p for p in row['provenance'] if p['provider'] == provider]
            if not row['source_records'].get(provider):
                latest_errors[(provider, statuses[-1]['status'] if statuses else 'not_requested')] += 1
    lines = ['# Seed-resolution checkpoint 1', '',
             f'Snapshot: `{snapshot}`. Private processing: private server. No site was published.', '',
             'Inputs are owner-supplied leads. Resolved metadata comes only from stored API responses. '
             'A review flag is not screening approval, and an unresolved result does not prove nonexistence.', '',
             '## Counts', '',
             f'- Input leads: {counts["input_seeds"]}.',
             f'- OpenAlex identities: {counts["resolved_openalex"]}/{counts["input_seeds"]}.',
             f'- Semantic Scholar identities: {counts["resolved_s2"]}/{counts["input_seeds"]}.',
             f'- Identities in both sources: {counts["both_providers"]}/{counts["input_seeds"]}.',
             f'- Name/title mismatch flags: {counts["title_mismatches"]}/{counts["input_seeds"]}.',
             '- Status totals: ' + ', '.join(f'{k}: {v}' for k, v in sorted(counts['by_status'].items())) + '.',
             '- Group totals: ' + ', '.join(f'{k}: {v}' for k, v in sorted(counts['by_group'].items())) + '.', '',
             '## Resolution table', '',
             '| Seed | Supplied name | Returned title | Year | OpenAlex | S2 | Status |',
             '|---|---|---|---:|---|---|---|']
    for row in records:
        oa = f'[{safe(row["openalex_id"].rsplit("/", 1)[-1])}]({row["openalex_id"]})' if row['openalex_id'] else '—'
        s2 = f'[{row["s2_paper_id"][:10]}](https://www.semanticscholar.org/paper/{row["s2_paper_id"]})' if row['s2_paper_id'] else '—'
        lines.append('| ' + ' | '.join([safe(row['seed_id']), safe(row['input']), safe(row['title']), safe(row['year']), oa, s2, safe(row['status'])]) + ' |')
    lines.extend(['', '## Items requiring review', ''])
    review_rows = [r for r in records if r['status'] != 'resolved']
    if not review_rows: lines.append('No record-level review flags were produced.')
    for row in review_rows:
        lines.extend([f'### {row["seed_id"]}: {safe(row["input"])}', '',
                      f'Returned title: {safe(row["title"])}. Status: `{row["status"]}`.', ''])
        for note in row['review_notes']: lines.append('- ' + safe(note))
        for provider, note in row['match_confidence_note'].items(): lines.append(f'- {provider}: {safe(note)}.')
        if not row['title']:
            for provider, candidates in row['unaccepted_candidates'].items():
                for candidate in candidates:
                    lines.append(f'- Unaccepted {provider} candidate: {safe(candidate["title"])} ({safe(candidate["year"])}), `{safe(candidate["id"])}`.')
        lines.append('')
    lines.extend(['## Missing provider identities', '',
                  'These are failures to establish an accepted identity, not evidence that a work does not exist. '
                  'Status 200 can still mean an empty or rejected title-search result; 429 is an API availability/rate-limit result.', '',
                  '| Provider | Last observed status | Leads without an accepted identity |', '|---|---:|---:|'])
    for (provider, status), count in sorted(latest_errors.items(), key=lambda item: str(item[0])):
        lines.append(f'| {provider} | {status} | {count} |')
    lines.extend(['', '## Provenance and next boundary', '',
                  f'Input SHA-256: `{data["input_sha256"]}`.', '',
                  'The JSON contains source-specific metadata, raw-response hashes, UTC retrieval times, '
                  'confidence notes and rejected candidates. The raw archive remains private on the server. '
                  'No abstracts or full texts were requested. No corpus expansion, embedding, relevance '
                  'threshold, graph layout or capability extraction has run.', '',
                  'Stop here for owner review. Expansion begins only after checkpoint-1 approval.'])
    (folder / 'SEED-RESOLUTION.md').write_text('\n'.join(lines) + '\n')
    return folder / 'SEED-RESOLUTION.md'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    args = parser.parse_args()
    print(report(args.snapshot))
