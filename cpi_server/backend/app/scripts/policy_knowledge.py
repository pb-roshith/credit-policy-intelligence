"""Export or seed portable policy knowledge without calling an AI provider."""
import argparse
import json
from pathlib import Path
from ..services.policy_knowledge_package import PACKAGE_DIR, export_package, import_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import'])
    parser.add_argument('--directory', type=Path, default=PACKAGE_DIR)
    parser.add_argument('--dry-run', action='store_true', help='Validate an import without writing database records')
    args = parser.parse_args()
    if args.action == 'export' and args.dry_run:
        parser.error('--dry-run applies to import only')
    result = export_package(args.directory) if args.action == 'export' else import_package(args.directory, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
