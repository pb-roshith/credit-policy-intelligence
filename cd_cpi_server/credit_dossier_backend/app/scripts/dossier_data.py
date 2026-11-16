"""Export the company list and documents, or load them into a fresh MCP database."""
import argparse
import json
from pathlib import Path
from app.services.dossier_data import package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export','import-mcp'])
    parser.add_argument('--directory', type=Path, default=None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'export':
        if args.dry_run:
            parser.error('Use --dry-run with an import action')
        result = package.export_package(args.directory)
    else:
        result = package.import_mcp(args.directory, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
