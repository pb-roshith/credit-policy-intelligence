"""Export current policy classification without modifying policy/database state.

Run from backend: .venv/Scripts/python.exe scripts/export_policy_taxonomy.py
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import SEED_OUTPUTS_DIR
from app.database import shared_policy_connection
from app.risk_knowledge.policy_taxonomy import current_taxonomy
from app.risk_knowledge.repositories import PostgreSQLRepository
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def cell(value):
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    # Preserve text as text, including source content starting with '='.
    return str(value)


def write_workbook(data, path):
    book = Workbook()
    book.remove(book.active)

    def sheet(name, columns, rows):
        ws = book.create_sheet(name)
        ws.append(columns)
        for row in rows:
            ws.append([cell(row.get(k)) for k in columns])
        for c in ws[1]:
            c.fill = PatternFill('solid', fgColor='173B50')
            c.font = Font(color='FFFFFF', bold=True)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, str):
                    c.data_type = 's'
                c.alignment = Alignment(vertical='top', wrap_text=True)
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for index, key in enumerate(columns, 1):
            ws.column_dimensions[get_column_letter(index)].width = 75 if key in ('passage', 'definition', 'methodology', 'path') else 28
        return ws

    sheet('Read me', ['item', 'value'], [
        {'item': 'Status', 'value': 'PROPOSED: review vocabulary and assignments before approval.'},
        {'item': 'Generated at UTC', 'value': data['generated_at']},
        {'item': 'Version', 'value': data['version']}, {'item': 'Source digest', 'value': data['source_digest']},
        *[{'item': key, 'value': value} for key, value in data['summary'].items()],
        *[{'item': 'Methodology', 'value': text} for text in data['methodology']],
        {'item': 'Full fidelity', 'value': 'JSON is the full machine-readable artifact. Workbook cells have the Excel 32,767-character limit.'},
    ])
    sheet('Dictionary', ['concept_id', 'preferred_name', 'kind', 'definition', 'inclusion_criteria', 'exclusion_criteria',
        'aliases', 'vocabulary_origin', 'review_status', 'support_status', 'support_count', 'schema_references'], data['dictionary'])
    sheet('Classification tree', ['node_id', 'parent_id', 'label', 'level', 'path', 'status', 'support_count', 'clause_ids'], data['tree'])
    flat = [{**a, **a['source'], 'path': ' > '.join(a['path'])} for a in data['assignments']]
    sheet('Clause assignments', ['assignment_id', 'path', 'category', 'topic', 'facets', 'status', 'document_name', 'policy_id',
        'policy_version_id', 'version', 'checksum', 'clause_id', 'clause', 'section', 'page', 'synthetic', 'content_role',
        'category_evidence_location', 'category_evidence', 'topic_evidence', 'interpretation', 'passage'], flat)
    sheet('Dimensions', ['dimension', 'value', 'support_count', 'status'], data['facets'])
    sheet('Dimension evidence', ['dimension', 'value', 'status', 'matches', 'clause_id', 'document_name', 'version', 'page', 'section', 'passage'],
        [{**e, **e['source']} for f in data['facets'] for e in f['evidence']])
    coverage = [{**r, **r['source']} for r in data['coverage']]
    columns = ['clause_id', 'policy_id', 'document_name', 'disposition', 'content_role', 'reason', 'facets', 'version', 'checksum', 'page', 'section', 'passage']
    sheet('Coverage', columns, coverage)
    sheet('Unclassified', columns, [r for r in coverage if r['disposition'] == 'UNCLASSIFIED'])
    sheet('Documents', ['policy_id', 'title', 'file_name', 'source_type', 'synthetic', 'policy_version_id', 'version',
        'checksum', 'content_digest', 'source_passages', 'source_status'], data['documents'])
    book.save(path)


def write_markdown(data, path):
    s = data['summary']
    lines = ['# Policy classification taxonomy', '',
        '**Status: PROPOSED — source-evidenced classifications for review.**', '',
        f"Generated: {data['generated_at']}. Version: {data['version']}.", '',
        f"{s['policies']} policies; {s['source_passages']} stored source passages; {s['classified_passages']} classified; "
        f"{s['structure_passages']} structural; {s['unclassified_passages']} unclassified.", '',
        f"{s['supported_concepts']} supported dictionary concepts; {s['unobserved_concepts']} unobserved; "
        f"{s['tree_nodes']} observed tree nodes; {s['assignments']} proposed assignments.", '',
        '[Open the review workbook](policy-taxonomy.xlsx) · [Full JSON](policy-taxonomy.json)', '',
        '## Method and limits', '', *['- ' + m for m in data['methodology']], '',
        '## Observed classification tree', '',
        'Each count is the number of distinct supporting passages. Unknown/multiple dimensions remain explicit.', '', '```text']
    children = defaultdict(list)
    for n in data['tree']:
        children[n['parent_id']].append(n)

    def branch(parent=None, indent=''):
        entries = sorted(children[parent], key=lambda n: n['label'])
        for index, n in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(indent + ('└── ' if last else '├── ') + n['label'] + f" [{n['support_count']}]")
            branch(n['node_id'], indent + ('    ' if last else '│   '))
    branch()
    lines.extend(['```', '', '## Controlled dictionary', '', '| Concept | Kind | Supporting passages | Status |', '|---|---|---:|---|'])
    lines.extend(f"| {c['preferred_name']} | {c['kind']} | {c['support_count']} | {c['support_status']} |" for c in data['dictionary'])
    lines.extend(['', '## Explicitly observed dimensions', ''])
    for dimension in sorted({f['dimension'] for f in data['facets']}):
        lines.append('- ' + dimension + ': ' + ', '.join(f"{f['value']} ({f['support_count']})" for f in data['facets'] if f['dimension'] == dimension))
    lines.extend(['', '## Source examples', ''])
    seen = set()
    for a in data['assignments']:
        if a['topic_id'] in seen or not a['topic_id']:
            continue
        seen.add(a['topic_id'])
        src = a['source']
        lines.extend(['**' + ' → '.join(a['path']) + '**', '',
            f"{src['document_name']} · version {src['version']} · {src['clause_id']} · page {src['page'] or 'not recorded'} · synthetic: {src['synthetic']}", '',
            '> ' + src['passage'][:900].replace('\n', '\n> ') + ('… [full passage in workbook/JSON]' if len(src['passage']) > 900 else ''), ''])
    lines.extend(['## Source inventory', '', '| Policy | Version | Passages | Synthetic | Source state |', '|---|---|---:|---|---|'])
    lines.extend(f"| {d['title']} | {d.get('version')} | {d['source_passages']} | {d['synthetic']} | {d['source_status']} |" for d in data['documents'])
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SEED_OUTPUTS_DIR / 'policy-taxonomy')
    args = parser.parse_args()
    schema = PostgreSQLRepository(shared_policy_connection, None).all('taxonomy_concepts')
    data = current_taxonomy(shared_policy_connection, schema)
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'policy-taxonomy.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    write_workbook(data, args.output / 'policy-taxonomy.xlsx')
    write_markdown(data, args.output / 'policy-taxonomy.md')
    print(json.dumps({'output': str(args.output.resolve()), **data['summary']}, indent=2))


if __name__ == '__main__':
    main()
