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
from .embedding_config import EmbeddingConfig
from .embedding_provider import create_embedding_provider
from .inspection import inspect_workbook, readable_summary, write_inventory
from .normalization import normalize_workbook
from .retrieval_evaluation import evaluate_retrieval_quality
from .paths import (
    DEFAULT_DOCUMENTS_PATH,
    DEFAULT_AI_MIGRATION_PATH,
    DEFAULT_INVENTORY_PATH,
    DEFAULT_MIGRATION_PATH,
    DEFAULT_SAMPLE_PATH,
    resolve_workbook_path,
)
from .validation import validate_documents, validate_jsonl, validate_relational
from .vector_store import (
    activate_embedding_profile,
    apply_ai_migration,
    embed_required_chunks,
    inspect_ai_catalog,
    register_embedding_profile,
    semantic_search,
    sync_vector_documents,
    validate_vector_layer,
)
from src.retrieval.authorization import cli_principal
from src.retrieval.evaluation import evaluate_routing
from src.retrieval.models import EntityHint, EntityType, RetrievalRequest, RouteMode
from src.retrieval.service import retrieve_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.retail_data_bootstrap",
        description="Retail 360 relational, semantic-document, and vector-layer tools.",
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
    commands.add_parser(
        "inspect-vector-database",
        help="Read the Azure SQL ai schema catalog without changing it.",
    )
    vector_migrate = commands.add_parser(
        "migrate-vector", help="Apply the additive ai vector schema migration."
    )
    vector_migrate.add_argument("--migration", type=Path, default=DEFAULT_AI_MIGRATION_PATH)
    commands.add_parser(
        "register-embedding-profile",
        help="Idempotently register the configured local BGE profile as BUILDING.",
    )
    sync = commands.add_parser(
        "sync-vector-documents",
        help="Validate and synchronize frozen semantic documents and deterministic chunks.",
    )
    sync.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    sync.add_argument("--dry-run", action="store_true")
    embed = commands.add_parser(
        "embed-vectors", help="Embed only missing or stale chunks for the configured profile."
    )
    embed.add_argument("--batch-size", type=int, default=16)
    vector_validate = commands.add_parser(
        "validate-vector-layer",
        help="Validate documents, chunks, profile linkage, native vectors, hashes, and norms.",
    )
    vector_validate.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    activate = commands.add_parser(
        "activate-vector-profile",
        help="Activate the configured profile only after full-corpus validation.",
    )
    activate.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    search = commands.add_parser(
        "search", help="Run service-level semantic search against the ACTIVE profile."
    )
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--domain", dest="retrieval_domain")
    search.add_argument("--doc-type")
    search.add_argument(
        "--allow-building",
        action="store_true",
        help="Search the configured BUILDING profile for sample validation only.",
    )
    evaluate_search = commands.add_parser(
        "evaluate-search",
        help="Run the deterministic/manual Phase 5 retrieval smoke-test set.",
    )
    evaluate_search.add_argument("--top-k", type=int, default=10)
    retrieve = commands.add_parser(
        "retrieve",
        help="Run deterministic SQL/vector/hybrid evidence retrieval.",
    )
    retrieve.add_argument("query")
    retrieve.add_argument(
        "--route",
        choices=[mode.value for mode in RouteMode],
        default=RouteMode.AUTO.value,
    )
    retrieve.add_argument("--top-k", type=int, default=5)
    retrieve.add_argument("--domain", dest="retrieval_domain")
    retrieve.add_argument("--doc-type")
    retrieve.add_argument(
        "--entity",
        action="append",
        default=[],
        metavar="TYPE=VALUE",
        help="Exact entity hint; TYPE is sku/store/vendor/legal_entity/category/brand/promotion.",
    )
    commands.add_parser(
        "evaluate-retrieval-routing",
        help="Evaluate the checked-in deterministic Phase 6 routing fixture.",
    )
    return parser


def _parse_entity_hints(values: list[str]) -> list[EntityHint]:
    hints: list[EntityHint] = []
    for value in values:
        entity_type, separator, raw = value.partition("=")
        if not separator or not raw.strip():
            raise ValueError("--entity must use TYPE=VALUE")
        hints.append(
            EntityHint(
                entity_type=EntityType(entity_type.strip().lower()),
                value=raw.strip(),
            )
        )
    return hints


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workbook_commands = {
        "inspect-workbook",
        "ingest-structured",
        "generate-documents",
        "validate",
    }
    workbook = None
    if args.command in workbook_commands:
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
    if args.command == "inspect-vector-database":
        catalog = inspect_ai_catalog()
        print(f"ai schema exists: {'yes' if catalog['schema_exists'] else 'no'}")
        print(f"ai table count: {len(catalog['tables'])}")
        for table, columns in catalog["tables"].items():
            print(f"- ai.{table}: {len(columns)} columns")
        return 0
    if args.command == "retrieve":
        request = RetrievalRequest(
            query=args.query,
            route_mode=args.route,
            top_k=args.top_k,
            retrieval_domain=args.retrieval_domain,
            doc_type=args.doc_type,
            entity_hints=_parse_entity_hints(args.entity),
        )
        result = retrieve_context(request, principal=cli_principal())
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0 if result.status.value != "FAILED" else 1
    if args.command == "evaluate-retrieval-routing":
        result = evaluate_routing()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    if args.command == "migrate-vector":
        result = apply_ai_migration(args.migration)
        print(
            f"Vector migration applied safely in {result['batch_count']} batches; "
            f"ai tables now present: {len(result['after']['tables'])}"
        )
        return 0
    config = EmbeddingConfig.from_env()
    if args.command == "register-embedding-profile":
        result = register_embedding_profile(config)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    provider = create_embedding_provider(config)
    if args.command == "sync-vector-documents":
        result = sync_vector_documents(
            args.documents, provider, config, dry_run=args.dry_run
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "embed-vectors":
        result = embed_required_chunks(
            provider, config, batch_size=args.batch_size
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "validate-vector-layer":
        result = validate_vector_layer(args.documents, provider, config)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["valid"] else 1
    if args.command == "activate-vector-profile":
        result = activate_embedding_profile(args.documents, provider, config)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "search":
        result = semantic_search(
            args.query,
            provider,
            config,
            top_k=args.top_k,
            retrieval_domain=args.retrieval_domain,
            doc_type=args.doc_type,
            allow_building=args.allow_building,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "evaluate-search":
        result = evaluate_retrieval_quality(
            provider, config, top_k=args.top_k
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["valid"] else 1
    return 2
