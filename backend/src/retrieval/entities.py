from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import EntityHint, EntityType, RecognizedEntity


@dataclass(frozen=True)
class EntityDefinition:
    entity_type: EntityType
    table: str
    id_column: str
    name_columns: tuple[str, ...]
    canonical_pattern: re.Pattern[str] | None = None


ENTITY_DEFINITIONS: dict[EntityType, EntityDefinition] = {
    EntityType.SKU: EntityDefinition(EntityType.SKU, "Sku", "sku_id", ("item_name",), re.compile(r"\b[A-Z]{3}-\d{3}\b", re.I)),
    EntityType.STORE: EntityDefinition(EntityType.STORE, "Store", "store_id", ("store_name",), re.compile(r"\bS\d{3}\b", re.I)),
    EntityType.VENDOR: EntityDefinition(EntityType.VENDOR, "Vendor", "vendor_account", ("vendor_name", "vendor_code"), re.compile(r"\bV\d{4}\b", re.I)),
    EntityType.LEGAL_ENTITY: EntityDefinition(EntityType.LEGAL_ENTITY, "LegalEntity", "legal_entity_id", ("legal_entity_name", "short_name")),
    EntityType.CATEGORY: EntityDefinition(EntityType.CATEGORY, "Category", "category_id", ("category_name",), re.compile(r"\b[A-Z]{3}-C\d{2}\b", re.I)),
    EntityType.BRAND: EntityDefinition(EntityType.BRAND, "Brand", "brand_name", ("brand_name",)),
    EntityType.PROMOTION: EntityDefinition(EntityType.PROMOTION, "Promotion", "promotion_id", ("promotion_name",), re.compile(r"\b(?:PRM|PROMO)-?\d{2,5}\b", re.I)),
}

MAX_ENTITY_NAME_SCAN_ROWS = 1000

CAPABILITY_REQUIRED_ENTITIES: dict[str, tuple[EntityType, ...]] = {
    "sku.lookup": (EntityType.SKU,),
    "sku.inventory_current": (EntityType.SKU,),
    "sku.replenishment_current": (EntityType.SKU,),
    "store.lookup": (EntityType.STORE,),
    "store_sku.snapshot": (EntityType.SKU, EntityType.STORE),
    "vendor.lookup": (EntityType.VENDOR,),
    "category.lookup": (EntityType.CATEGORY,),
    "brand.lookup": (EntityType.BRAND,),
    "legal_entity.lookup": (EntityType.LEGAL_ENTITY,),
    "promotion.lookup": (EntityType.PROMOTION,),
    "workforce.current": (EntityType.STORE,),
    "sales.monthly": (EntityType.LEGAL_ENTITY,),
    "trade_agreement.by_vendor": (EntityType.VENDOR,),
    "inventory.at_risk": (),
    "replenishment.top_candidates": (),
}


@dataclass
class EntityResolution:
    entities: list[RecognizedEntity] = field(default_factory=list)
    missing: list[EntityType] = field(default_factory=list)
    ambiguous: dict[EntityType, list[dict[str, str]]] = field(default_factory=dict)

    @property
    def by_type(self) -> dict[EntityType, RecognizedEntity]:
        return {entity.entity_type: entity for entity in self.entities}


def required_entity_types(capabilities: list[str]) -> tuple[EntityType, ...]:
    result: list[EntityType] = []
    for capability in capabilities:
        for entity_type in CAPABILITY_REQUIRED_ENTITIES.get(capability, ()):
            if entity_type not in result:
                result.append(entity_type)
    return tuple(result)


def _description_names(cursor) -> list[str]:
    return [str(column[0]) for column in cursor.description]


def _fetch_candidates(cursor, definition: EntityDefinition, value: str) -> list[dict[str, str]]:
    comparisons = [f"UPPER([{definition.id_column}]) = UPPER(?)"]
    params: list[Any] = [value]
    for column in definition.name_columns:
        if column == definition.id_column:
            continue
        comparisons.append(f"UPPER([{column}]) = UPPER(?)")
        params.append(value)
    selected = [definition.id_column, *definition.name_columns]
    selected = list(dict.fromkeys(selected))
    cursor.execute(
        f"SELECT TOP (6) {', '.join(f'[{name}]' for name in selected)} "
        f"FROM retail.[{definition.table}] WHERE {' OR '.join(comparisons)} "
        f"ORDER BY [{definition.id_column}];",
        tuple(params),
    )
    names = _description_names(cursor)
    return [
        {name: str(value) if value is not None else "" for name, value in zip(names, row)}
        for row in cursor.fetchall()
    ]


def _all_names_in_query(cursor, definition: EntityDefinition, query: str) -> list[dict[str, str]]:
    selected = [definition.id_column, *definition.name_columns]
    selected = list(dict.fromkeys(selected))
    cursor.execute(
        f"SELECT TOP ({MAX_ENTITY_NAME_SCAN_ROWS}) "
        f"{', '.join(f'[{name}]' for name in selected)} "
        f"FROM retail.[{definition.table}] ORDER BY [{definition.id_column}];"
    )
    names = _description_names(cursor)
    rows = [
        {name: str(value) if value is not None else "" for name, value in zip(names, row)}
        for row in cursor.fetchall()
    ]
    normalized_query = " ".join(query.casefold().split())
    matches: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        candidate_names = [row.get(column, "") for column in definition.name_columns]
        lengths = [
            len(normalized)
            for name in candidate_names
            if (normalized := " ".join(name.casefold().split()))
            and re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", normalized_query)
        ]
        if lengths:
            matches.append((max(lengths), row))
    if not matches:
        return []
    longest = max(length for length, _ in matches)
    return [row for length, row in matches if length == longest][:6]


class EntityResolver:
    def resolve(
        self,
        query: str,
        hints: list[EntityHint],
        required_types: tuple[EntityType, ...],
        connection,
    ) -> EntityResolution:
        resolution = EntityResolution()
        hinted: dict[EntityType, list[str]] = {}
        for hint in hints:
            hinted.setdefault(hint.entity_type, []).append(hint.value.strip())

        types: list[EntityType] = list(required_types)
        for entity_type in hinted:
            if entity_type not in types:
                types.append(entity_type)
        for entity_type, definition in ENTITY_DEFINITIONS.items():
            if definition.canonical_pattern and definition.canonical_pattern.search(query):
                if entity_type not in types:
                    types.append(entity_type)

        cursor = connection.cursor()
        for entity_type in types:
            definition = ENTITY_DEFINITIONS[entity_type]
            raw_values = hinted.get(entity_type, [])
            if not raw_values and definition.canonical_pattern:
                raw_values = list(dict.fromkeys(match.group(0) for match in definition.canonical_pattern.finditer(query)))
            if len(raw_values) > 1:
                resolution.ambiguous[entity_type] = [
                    {"identifier": value, "display_name": value}
                    for value in raw_values[:5]
                ]
                continue
            method = "canonical_identifier"
            if raw_values:
                candidates = _fetch_candidates(cursor, definition, raw_values[0])
                if entity_type in hinted:
                    method = "exact_hint"
            else:
                candidates = _all_names_in_query(cursor, definition, query)
                method = "exact_name_in_query"
            if len(candidates) == 1:
                row = candidates[0]
                identifier = row[definition.id_column]
                display = next(
                    (row[column] for column in definition.name_columns if row.get(column)),
                    identifier,
                )
                resolution.entities.append(
                    RecognizedEntity(
                        entity_type=entity_type,
                        identifier=identifier,
                        display_name=display,
                        resolution_method=method,
                    )
                )
            elif len(candidates) > 1:
                resolution.ambiguous[entity_type] = [
                    {
                        "identifier": row[definition.id_column],
                        "display_name": next(
                            (row[column] for column in definition.name_columns if row.get(column)),
                            row[definition.id_column],
                        ),
                    }
                    for row in candidates[:5]
                ]
            elif entity_type in required_types:
                resolution.missing.append(entity_type)
        return resolution
