"""Back up and remove assessments containing rule versions no longer in inventory."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import BACKUP_DIR
from app.database import shared_policy_connection


def main():
    with shared_policy_connection() as connection:
        reviews = connection.execute('''SELECT * FROM "user".ai_compliance_reviews a
            WHERE EXISTS (
                SELECT 1 FROM (
                    SELECT s->>'id' AS id FROM jsonb_array_elements(a.review->'rule_snapshots') s
                    UNION SELECT f->>'rule_version_id' FROM jsonb_array_elements(a.review->'findings') f
                ) refs WHERE refs.id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM policy_rule_versions r WHERE r.id=refs.id::bigint))
            FOR UPDATE''').fetchall()
        if not reviews:
            print('No stale assessments found.')
            return
        # Pair account and review identifiers throughout the cleanup.
        connection.execute('CREATE TEMP TABLE stale_assessment_keys (user_id text, review_id bigint) ON COMMIT DROP')
        for row in reviews:
            connection.execute('INSERT INTO stale_assessment_keys VALUES (%s,%s)', (row['user_id'], row['review_id']))
        runs = connection.execute('''SELECT r.* FROM "user".rule_assessment_runs r
            JOIN stale_assessment_keys s USING(user_id,review_id)''').fetchall()
        backup = {'created_at': datetime.now(timezone.utc).isoformat(), 'reviews': reviews, 'runs': runs}
        for table in ('policy_request_mappings', 'request_rule_assessments'):
            backup[table] = connection.execute(f'''SELECT d.* FROM "user".{table} d
                JOIN "user".rule_assessment_runs r ON r.user_id=d.user_id AND r.id=d.run_id
                JOIN stale_assessment_keys s ON s.user_id=r.user_id AND s.review_id=r.review_id''').fetchall()
        backup['mapping_cache'] = connection.execute('''SELECT m.* FROM "user".request_policy_mapping_cache m
            JOIN stale_assessment_keys s ON s.user_id=m.user_id AND s.review_id::text=m.report->>'review_id' ''').fetchall()
        path = BACKUP_DIR / ('stale-assessments-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8] + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as output:
            json.dump(backup, output, default=str, indent=2)
        for table in ('policy_request_mappings', 'request_rule_assessments'):
            connection.execute(f'''DELETE FROM "user".{table} d USING "user".rule_assessment_runs r, stale_assessment_keys s
                WHERE d.user_id=r.user_id AND d.run_id=r.id AND s.user_id=r.user_id AND s.review_id=r.review_id''')
        connection.execute('''DELETE FROM "user".request_policy_mapping_cache m USING stale_assessment_keys s
            WHERE s.user_id=m.user_id AND s.review_id::text=m.report->>'review_id' ''')
        connection.execute('''DELETE FROM "user".rule_assessment_runs r USING stale_assessment_keys s
            WHERE s.user_id=r.user_id AND s.review_id=r.review_id''')
        connection.execute('''DELETE FROM "user".ai_compliance_reviews a USING stale_assessment_keys s
            WHERE s.user_id=a.user_id AND s.review_id=a.review_id''')
    print(json.dumps({'removed_assessments': len(reviews), 'removed_runs': len(runs),
                      'removed_mapping_caches': len(backup['mapping_cache']), 'backup': str(path)}))


if __name__ == '__main__':
    main()
