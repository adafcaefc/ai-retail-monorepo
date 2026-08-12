from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database import (
    apply_migration,
    ingest_structured,
    inspect_catalog,
    validate_live_relational,
)
from .documents import build_documents, representative_sample, write_jsonl
from .inspection import inspect_workbook, readable_summary, write_inventory
from .normalization import normalize_workbook
from .paths import (
    DEFAULT_DOCUMENTS_PATH,
    DEFAULT_INVENTORY_PATH,
    DEFAULT_MIGRATION_PATH,
    DEFAULT_SAMPLE_PATH,
    resolve_workbook_path,
)
from .validation import validate_documents, validate_jsonl, validate_relational


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.retail_data_bootstrap",
        description="Retail 360 pre-embedding data foundation tools.",
    )
    parser.add_argument("--workbook", type=Path, help="Override the source workbook path.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-workbook", help="Inventory and classify every worksheet.")
    inspect.add_argument("--output", type=Path, default=DEFAULT_INVENTORY_PATH)
    commands.add_parser("inspect-database", help="Read the Azure SQL retail schema catalog without changing it.")
    migrate = commands.add_parser("migrate", help="Apply the additive retail schema migration.")
    migrate.add_argument("--migration", type=Path, default=DEFAULT_MIGRATION_PATH)
    ingest = commands.add_parser("ingest-structured", help="Normalize and upsert structured workbook facts.")
    ingest.add_argument("--dry-run", action="store_true")
    generate = commands.add_parser("generate-documents", help="Build and validate semantic JSONL without embeddings.")
    generate.add_argument("--output", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    generate.add_argument("--sample-output", type=Path, default=DEFAULT_SAMPLE_PATH)
    generate.add_argument("--sample-only", action="store_true")
    validate = commands.add_parser("validate", help="Validate normalized relational data and generated JSONL.")
    validate.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    validate.add_argument("--live", action="store_true", help="Also validate loaded Azure SQL rows and constraints.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workbook = resolve_workbook_path(args.workbook)
    if not workbook.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    if args.command == "inspect-workbook":
        report = inspect_workbook(workbook)
        write_inventory(report, args.output)
        print(readable_summary(report))
        print(f"\nMachine-readable inventory: {args.output.resolve()}")
        return 0
    if args.command == "inspect-database":
        catalog = inspect_catalog()
        print(f"retail schema exists: {'yes' if catalog['schema_exists'] else 'no'}")
        print(f"retail table count: {len(catalog['tables'])}")
        for table, columns in catalog["tables"].items():
            print(f"- retail.{table}: {len(columns)} columns")
        return 0
    if args.command == "migrate":
        result = apply_migration(args.migration)
        print(
            f"Migration applied safely in {result['batch_count']} batches; "
            f"retail tables now present: {len(result['after']['tables'])}"
        )
        return 0
    if args.command == "ingest-structured":
        dataset = normalize_workbook(workbook)
        result = ingest_structured(dataset, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "generate-documents":
        documents = build_documents(workbook)
        sample = representative_sample(documents)
        sample_validation = validate_documents(sample)
        if not sample_validation["valid"]:
            print(json.dumps(sample_validation, ensure_ascii=False, indent=2))
            return 1
        write_jsonl(sample, args.sample_output)
        if args.sample_only:
            print(json.dumps(sample_validation, ensure_ascii=False, indent=2))
            print(f"Sample JSONL: {args.sample_output.resolve()}")
            return 0
        validation = validate_documents(documents)
        if not validation["valid"]:
            print(json.dumps(validation, ensure_ascii=False, indent=2))
            return 1
        write_jsonl(documents, args.output)
        jsonl_validation = validate_jsonl(args.output)
        result = {"documents": validation, "jsonl": jsonl_validation}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Full JSONL: {args.output.resolve()}")
        return 0 if jsonl_validation["valid"] else 1
    if args.command == "validate":
        dataset = normalize_workbook(workbook)
        result: dict[str, object] = {"relational": validate_relational(dataset)}
        if args.documents.is_file():
            result["jsonl"] = validate_jsonl(args.documents)
        else:
            result["jsonl"] = {"valid": False, "errors": [f"Missing {args.documents}"]}
        if args.live:
            result["azure_sql"] = validate_live_relational(dataset)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if all(section.get("valid") for section in result.values()) else 1
    return 2
