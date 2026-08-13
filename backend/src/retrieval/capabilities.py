from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .models import EntityType, SourceReference, StructuredResult

DEFAULT_SQL_ROW_LIMIT = 20
MAX_SQL_ROW_LIMIT = 50


@dataclass(frozen=True)
class SqlCapability:
    key: str
    intent: str
    required_entities: tuple[EntityType, ...]
    tables: tuple[str, ...]
    query: str
    parameter_entities: tuple[EntityType, ...] = ()
    has_limit_parameter: bool = False
    max_rows: int = DEFAULT_SQL_ROW_LIMIT
    business_key_fields: tuple[str, ...] = ()
    selected_fields: tuple[str, ...] = ()


LINEAGE_FIELDS = ("source_load_id", "source_sheet", "source_row", "loaded_at")

CAPABILITIES: dict[str, SqlCapability] = {}


def _register(capability: SqlCapability) -> None:
    CAPABILITIES[capability.key] = capability


_register(SqlCapability(
    key="sku.lookup", intent="Exact SKU master lookup", required_entities=(EntityType.SKU,),
    tables=("Sku",), parameter_entities=(EntityType.SKU,), max_rows=1,
    business_key_fields=("sku_id",),
    selected_fields=("sku_id", "item_name", "legal_entity_id", "category_id", "is_perishable", "price", "cost", "margin_pct", "sales_uom", "buy_uom", "pack_factor", "channel", "vendor_account", "brand_name"),
    query="""SELECT s.sku_id,s.item_name,s.legal_entity_id,s.category_id,s.is_perishable,s.price,s.cost,s.margin_pct,s.sales_uom,s.buy_uom,s.pack_factor,s.channel,s.vendor_account,s.brand_name,s.source_load_id,s.source_sheet,s.source_row,s.loaded_at FROM retail.Sku AS s WHERE UPPER(s.sku_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="sku.inventory_current", intent="Exact current SKU inventory evidence", required_entities=(EntityType.SKU,),
    tables=("Sku", "InventorySnapshot"), parameter_entities=(EntityType.SKU,), max_rows=1,
    business_key_fields=("sku_id",),
    selected_fields=("sku_id", "item_name", "legal_entity_id", "category_id", "vendor_account", "brand_name", "ads", "inventory_position", "reorder_point", "max_inventory", "days_of_supply", "inventory_state", "price", "inventory_value", "at_risk_value", "expiry_units", "order_units", "order_value", "weekly_gmv", "margin_amount", "funding_amount", "open_po_units"),
    query="""SELECT s.sku_id,s.item_name,s.legal_entity_id,s.category_id,s.vendor_account,s.brand_name,i.ads,i.inventory_position,i.reorder_point,i.max_inventory,i.days_of_supply,i.inventory_state,i.price,i.inventory_value,i.at_risk_value,i.expiry_units,i.order_units,i.order_value,i.weekly_gmv,i.margin_amount,i.funding_amount,i.open_po_units,i.source_load_id,i.source_sheet,i.source_row,i.loaded_at FROM retail.InventorySnapshot AS i JOIN retail.Sku AS s ON s.sku_id=i.sku_id WHERE UPPER(i.sku_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="sku.replenishment_current", intent="Exact current SKU replenishment proposal", required_entities=(EntityType.SKU,),
    tables=("Sku", "ReplenishmentProposal"), parameter_entities=(EntityType.SKU,), max_rows=1,
    business_key_fields=("sku_id",),
    selected_fields=("sku_id", "item_name", "reorder_required", "order_sales_units", "buy_uom", "order_buy_units", "designated_vendor_account", "designated_unit_price", "amount", "best_price_vendor_account", "best_price", "saving_vs_designated"),
    query="""SELECT r.sku_id,s.item_name,r.reorder_required,r.order_sales_units,r.buy_uom,r.order_buy_units,r.designated_vendor_account,r.designated_unit_price,r.amount,r.best_price_vendor_account,r.best_price,r.saving_vs_designated,r.source_load_id,r.source_sheet,r.source_row,r.loaded_at FROM retail.ReplenishmentProposal AS r JOIN retail.Sku AS s ON s.sku_id=r.sku_id WHERE UPPER(r.sku_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="store.lookup", intent="Exact store master lookup", required_entities=(EntityType.STORE,),
    tables=("Store",), parameter_entities=(EntityType.STORE,), max_rows=1,
    business_key_fields=("store_id",),
    selected_fields=("store_id", "store_name", "legal_entity_id", "cluster", "size_factor", "health_factor", "footfall_index", "channel"),
    query="""SELECT store_id,store_name,legal_entity_id,cluster,size_factor,health_factor,footfall_index,channel,source_load_id,source_sheet,source_row,loaded_at FROM retail.Store WHERE UPPER(store_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="store_sku.snapshot", intent="Exact current SKU/store snapshot", required_entities=(EntityType.SKU, EntityType.STORE),
    tables=("StoreSkuSnapshot",), parameter_entities=(EntityType.SKU, EntityType.STORE), max_rows=1,
    business_key_fields=("sku_id", "store_id"),
    selected_fields=("sku_id", "store_id", "ads", "on_hand_units", "open_po_units", "inventory_position", "reorder_point", "max_inventory", "days_of_supply", "inventory_state", "price", "inventory_value", "at_risk_value", "forecast_7d", "order_sales_units", "pack_factor", "order_buy_units", "order_value", "promo_incremental_margin", "contribution_per_day", "labour_fte"),
    query="""SELECT sku_id,store_id,ads,on_hand_units,open_po_units,inventory_position,reorder_point,max_inventory,days_of_supply,inventory_state,price,inventory_value,at_risk_value,forecast_7d,order_sales_units,pack_factor,order_buy_units,order_value,promo_incremental_margin,contribution_per_day,labour_fte,source_load_id,source_sheet,source_row,loaded_at FROM retail.StoreSkuSnapshot WHERE UPPER(sku_id)=UPPER(?) AND UPPER(store_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="vendor.lookup", intent="Exact current vendor master/service evidence", required_entities=(EntityType.VENDOR,),
    tables=("Vendor",), parameter_entities=(EntityType.VENDOR,), max_rows=1,
    business_key_fields=("vendor_account",),
    selected_fields=("vendor_account", "vendor_code", "vendor_name", "vendor_group", "currency", "payment_terms", "delivery_terms", "lead_time_days", "moq_units", "otif_pct", "fill_pct", "defect_pct", "lead_adherence_pct"),
    query="""SELECT vendor_account,vendor_code,vendor_name,vendor_group,currency,payment_terms,delivery_terms,lead_time_days,moq_units,otif_pct,fill_pct,defect_pct,lead_adherence_pct,source_load_id,source_sheet,source_row,loaded_at FROM retail.Vendor WHERE UPPER(vendor_account)=UPPER(?);""",
))
_register(SqlCapability(
    key="category.lookup", intent="Exact category master lookup", required_entities=(EntityType.CATEGORY,),
    tables=("Category",), parameter_entities=(EntityType.CATEGORY,), max_rows=1,
    business_key_fields=("category_id",),
    selected_fields=("category_id", "legal_entity_id", "category_name", "is_perishable"),
    query="""SELECT category_id,legal_entity_id,category_name,is_perishable,source_load_id,source_sheet,source_row,loaded_at FROM retail.Category WHERE UPPER(category_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="brand.lookup", intent="Exact brand master lookup", required_entities=(EntityType.BRAND,),
    tables=("Brand",), parameter_entities=(EntityType.BRAND,), max_rows=1,
    business_key_fields=("brand_name",),
    selected_fields=("brand_name",),
    query="""SELECT brand_name,source_load_id,source_sheet,source_row,loaded_at FROM retail.Brand WHERE UPPER(brand_name)=UPPER(?);""",
))
_register(SqlCapability(
    key="legal_entity.lookup", intent="Exact legal-entity master lookup", required_entities=(EntityType.LEGAL_ENTITY,),
    tables=("LegalEntity",), parameter_entities=(EntityType.LEGAL_ENTITY,), max_rows=1,
    business_key_fields=("legal_entity_id",),
    selected_fields=("legal_entity_id", "legal_entity_name", "short_name", "workforce_base_per_size", "sales_per_fte", "peak_season_factor", "total_store_size"),
    query="""SELECT legal_entity_id,legal_entity_name,short_name,workforce_base_per_size,sales_per_fte,peak_season_factor,total_store_size,source_load_id,source_sheet,source_row,loaded_at FROM retail.LegalEntity WHERE UPPER(legal_entity_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="promotion.lookup", intent="Exact promotion configuration lookup", required_entities=(EntityType.PROMOTION,),
    tables=("Promotion",), parameter_entities=(EntityType.PROMOTION,), max_rows=1,
    business_key_fields=("promotion_id",),
    selected_fields=("promotion_id", "promotion_name", "discount_type", "scope", "legal_entity_id", "target_category", "season", "peak_month", "mechanism", "discount_pct", "value_rule", "min_quantity_threshold", "supplier_funding_pct", "expected_uplift_pct", "prebuy_uplift_units", "valid_from", "valid_to", "d365_construct"),
    query="""SELECT promotion_id,promotion_name,discount_type,scope,legal_entity_id,target_category,season,peak_month,mechanism,discount_pct,value_rule,min_quantity_threshold,supplier_funding_pct,expected_uplift_pct,prebuy_uplift_units,valid_from,valid_to,d365_construct,source_load_id,source_sheet,source_row,loaded_at FROM retail.Promotion WHERE UPPER(promotion_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="workforce.current", intent="Exact current store workforce snapshot", required_entities=(EntityType.STORE,),
    tables=("WorkforceSnapshot",), parameter_entities=(EntityType.STORE,), max_rows=1,
    business_key_fields=("store_id",),
    selected_fields=("store_id", "event_name", "event_lift", "workforce_base", "peak_factor", "scheduled_fte", "required_fte", "gap_fte", "surplus_fte", "coverage_pct"),
    query="""SELECT store_id,event_name,event_lift,workforce_base,peak_factor,scheduled_fte,required_fte,gap_fte,surplus_fte,coverage_pct,source_load_id,source_sheet,source_row,loaded_at FROM retail.WorkforceSnapshot WHERE UPPER(store_id)=UPPER(?);""",
))
_register(SqlCapability(
    key="sales.monthly", intent="Bounded monthly sales history for one legal entity", required_entities=(EntityType.LEGAL_ENTITY,),
    tables=("MonthlySales",), parameter_entities=(EntityType.LEGAL_ENTITY,), has_limit_parameter=True, max_rows=24,
    business_key_fields=("period_label", "legal_entity_id"),
    selected_fields=("period_label", "legal_entity_id", "sales_amount"),
    query="""SELECT TOP (?) period_label,legal_entity_id,sales_amount,source_load_id,source_sheet,source_row,loaded_at FROM retail.MonthlySales WHERE UPPER(legal_entity_id)=UPPER(?) ORDER BY source_row DESC,period_label DESC;""",
))
_register(SqlCapability(
    key="trade_agreement.by_vendor", intent="Bounded exact trade agreement records for a vendor", required_entities=(EntityType.VENDOR,),
    tables=("TradeAgreement",), parameter_entities=(EntityType.VENDOR,), has_limit_parameter=True, max_rows=20,
    business_key_fields=("sku_id", "vendor_account", "valid_from", "min_quantity"),
    selected_fields=("sku_id", "vendor_account", "valid_from", "min_quantity", "item_name", "unit_price", "currency", "lead_time_days", "discount_pct", "valid_to", "is_designated"),
    query="""SELECT TOP (?) sku_id,vendor_account,valid_from,min_quantity,item_name,unit_price,currency,lead_time_days,discount_pct,valid_to,is_designated,source_load_id,source_sheet,source_row,loaded_at FROM retail.TradeAgreement WHERE UPPER(vendor_account)=UPPER(?) ORDER BY sku_id,valid_from DESC,min_quantity;""",
))
_register(SqlCapability(
    key="inventory.at_risk", intent="Bounded ranking by exact structured at-risk inventory value", required_entities=(),
    tables=("Sku", "InventorySnapshot"), has_limit_parameter=True, max_rows=20,
    business_key_fields=("sku_id",),
    selected_fields=("sku_id", "item_name", "inventory_state", "inventory_position", "reorder_point", "days_of_supply", "at_risk_value", "inventory_value"),
    query="""SELECT TOP (?) i.sku_id,s.item_name,i.inventory_state,i.inventory_position,i.reorder_point,i.days_of_supply,i.at_risk_value,i.inventory_value,i.source_load_id,i.source_sheet,i.source_row,i.loaded_at FROM retail.InventorySnapshot AS i JOIN retail.Sku AS s ON s.sku_id=i.sku_id ORDER BY COALESCE(i.at_risk_value,0) DESC,i.sku_id;""",
))
_register(SqlCapability(
    key="replenishment.top_candidates", intent="Bounded ranking by exact proposed replenishment quantity", required_entities=(),
    tables=("Sku", "ReplenishmentProposal"), has_limit_parameter=True, max_rows=20,
    business_key_fields=("sku_id",),
    selected_fields=("sku_id", "item_name", "reorder_required", "order_sales_units", "buy_uom", "order_buy_units", "amount"),
    query="""SELECT TOP (?) r.sku_id,s.item_name,r.reorder_required,r.order_sales_units,r.buy_uom,r.order_buy_units,r.amount,r.source_load_id,r.source_sheet,r.source_row,r.loaded_at FROM retail.ReplenishmentProposal AS r JOIN retail.Sku AS s ON s.sku_id=r.sku_id WHERE r.reorder_required=1 ORDER BY COALESCE(r.order_buy_units,0) DESC,r.sku_id;""",
))


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _citation_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sql:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class StructuredSqlExecutor:
    def execute(
        self,
        capability_key: str,
        entities: dict[EntityType, Any],
        connection,
        *,
        row_limit: int = DEFAULT_SQL_ROW_LIMIT,
    ) -> tuple[list[StructuredResult], list[SourceReference], bool]:
        capability = CAPABILITIES[capability_key]
        limit = min(max(1, row_limit), capability.max_rows, MAX_SQL_ROW_LIMIT)
        params: list[Any] = []
        if capability.has_limit_parameter:
            params.append(limit)
        for entity_type in capability.parameter_entities:
            params.append(entities[entity_type].identifier)
        cursor = connection.cursor()
        cursor.execute(capability.query, tuple(params))
        columns = [str(column[0]) for column in cursor.description]
        rows = cursor.fetchall()
        results: list[StructuredResult] = []
        citations: list[SourceReference] = []
        for index, raw in enumerate(rows, 1):
            row = {name: _json_value(value) for name, value in zip(columns, raw)}
            data = {name: row.get(name) for name in capability.selected_fields}
            business_keys = {name: row.get(name) for name in capability.business_key_fields}
            identity = {
                "capability_key": capability.key,
                "business_keys": business_keys,
                "source_load_id": row.get("source_load_id"),
                "source_sheet": row.get("source_sheet"),
                "source_row": row.get("source_row"),
            }
            citation_id = _citation_id(identity)
            citation = SourceReference(
                citation_id=citation_id,
                source_kind="sql",
                schema_name="retail",
                tables=list(capability.tables),
                business_keys=business_keys,
                capability_key=capability.key,
                selected_fields=list(capability.selected_fields),
                source_load_id=int(row["source_load_id"]) if row.get("source_load_id") is not None else None,
                source_sheet=str(row["source_sheet"]) if row.get("source_sheet") is not None else None,
                source_row=int(row["source_row"]) if row.get("source_row") is not None else None,
                source_load_at=str(row["loaded_at"]) if row.get("loaded_at") is not None else None,
            )
            citations.append(citation)
            results.append(
                StructuredResult(
                    capability_key=capability.key,
                    row_index=index,
                    data=data,
                    citation_ids=[citation_id],
                )
            )
        limit_applied = capability.has_limit_parameter and len(rows) == limit
        return results, citations, limit_applied


def capability_catalog() -> list[dict[str, Any]]:
    return [
        {
            "capability_key": value.key,
            "intent": value.intent,
            "required_entities": [item.value for item in value.required_entities],
            "source_tables": [f"retail.{table}" for table in value.tables],
            "returned_fields": list(value.selected_fields),
            "max_rows": value.max_rows,
        }
        for value in CAPABILITIES.values()
    ]
