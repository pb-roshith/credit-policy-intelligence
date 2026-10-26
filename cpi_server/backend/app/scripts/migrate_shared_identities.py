"""Migrate legacy CPI identities without moving their business records.

Run from cpi_server/backend:
python -m app.scripts.migrate_shared_identities --apply --replace-duplicates aegon hela romi

Without --apply, only prints the account inventory. Hashes never appear in output.
Replacement must name each explicitly authorized duplicate; linked Dossier rows remain.
"""
import argparse
import json
from ..database import db_connection
from ..services.dossier_identity import identity_call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--replace-duplicates', nargs='*', default=[])
    args = parser.parse_args()
    replacements = {name.casefold() for name in args.replace_duplicates}
    with db_connection() as connection:
        rows = connection.execute("SELECT * FROM public.users WHERE auth_provider='local' AND role IN ('relationship_manager','credit_analyst') ORDER BY user_id").fetchall()
    for row in rows:
        name = row['user_id']
        if not args.apply:
            print(name, row['role'], 'replace Dossier duplicate' if name.casefold() in replacements else 'import if unique')
            continue
        questions = json.loads(row['questions'])
        result = identity_call(name, {
            'user_id':name, 'source_id':name, 'password_hash':row['password_hash'],
            'role':row['role'], 'approved':row['status']=='approved','locked':bool(row['locked']),
            'security_answers':questions,'replace_existing':name.casefold() in replacements,
        }, 'import')
        with db_connection() as connection:
            # Preserve local identity spelling and every account-owned foreign key.
            connection.execute("""UPDATE public.users SET auth_provider='dossier',dossier_user_id=%s,
                dossier_credential_version=%s,password_hash='!dossier-managed!',questions='[]'
                WHERE user_id=%s AND auth_provider='local'""",
                (result['user_id'],result['credential_version'],name))
            connection.execute('DELETE FROM public.sessions WHERE user_id=%s',(name,))
        print(name + ': ' + result['status'])


if __name__ == '__main__':
    main()
