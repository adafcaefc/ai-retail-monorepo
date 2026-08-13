# Retail Data and Vector Bootstrap — Pre-Embedding Foundation

## 1. Objective

Build and validate the pre-embedding data foundation for AI Retail 360: inspect and classify every workbook sheet, normalize supported structured data into Azure SQL under `retail.*`, generate traceable semantic documents and a JSONL preview corpus, and validate both layers without generating embeddings or creating/populating a vector table.

## 2. Current Architecture

- Excel is the temporary source adapter input. The current workbook is `resources/Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`.
- Azure SQL `retail.*` is the structured relational facts layer for exact filters, joins, aggregates, and calculations.
- A future Azure SQL `ai.*` layer will hold semantic documents, embeddings, and vector-search support. That layer is explicitly out of scope for this phase.
- The backend will eventually choose exact SQL, vector retrieval, or a hybrid of both. This phase does not connect the new foundation to application endpoints, frontend behavior, or agent chat.
- Source-specific extraction is separated from source-neutral normalized records, relational loading, and semantic document generation so Excel can later be replaced by D365/ERP without redesigning the downstream contracts.

## 3. Workbook Inventory

The reusable command `cd backend && python -m src.retail_data_bootstrap inspect-workbook` writes the complete machine-readable profile to `generated/workbook_inventory.json`. That report also contains inferred types, per-column null counts, duplicate examples, representative rows, formula cell examples, and the 12 value-proven relationships. Generated artifacts are intentionally Git-ignored.

| Sheet | Rows × columns | Normalized columns | Candidate key(s) | Formulas | Orientation |
|---|---:|---|---|---:|---|
| `LISTING` | 49 × 3 | `no`, `sheet`, `description` | `no`; `sheet` (both unique) | No | documentation |
| `Cover & Storyline` | 11 × 10 | narrative column plus nine empty layout columns | None | No | documentation |
| `Constants` | 21 × 4 | `parameter`, `value`, two empty layout columns | `parameter` (unique) | No | source |
| `Verticals` | 13 × 7 | `id`, `vertical`, `short`, `wf_base_size`, `sales_per_fte`, `peak_season`, `store_size` | `id`; `vertical` (both unique) | No | source |
| `Stores` | 165 × 8 | `store_id`, `vertical`, `store_name`, `cluster`, `size`, `health`, `footfall_idx`, `channel` | `store_id` (unique) | No | source |
| `Categories` | 165 × 4 | `cat_id`, `vertical`, `category`, `perishable` | `cat_id` (unique) | No | source |
| `Main Vendor` | 13 × 13 | `vendor_account`, `vendor`, `vendor_name`, `group`, `currency`, `payment_terms`, `delivery_terms`, `lead_time_d`, `moq_units`, `otif`, `fill`, `defect`, `lead_adherence` | `vendor_account`; `vendor` (both unique) | No | source |
| `Trade Agreement` | 2,405 × 12 | `item`, `item_name`, `vendor_account`, `vendor`, `unit_price`, `currency`, `min_qty_break`, `lead_time_d`, `discount`, `valid_from`, `valid_to`, `designated` | `item + vendor_account + valid_from + min_qty_break` (unique) | No | source |
| `SKU_Master` | 805 × 32 | `sku_id`, `vertical`, `cat_id`, `category`, `item`, `perishable`, `base_ads`, `price`, `margin`, `cost`, `lead_d`, `onhand_days`, `open_po`, `safety_d`, `expiry_d`, `growth`, `elasticity`, `comp_idx`, `fund`, `cannib`, `promo`, `viral`, `sales_uom`, `buy_uom`, `pack_factor`, `channel`, `seasonality`, `stockf`, `vert_size`, `sales_fte`, `vendor`, `brand` | `sku_id` (unique) | No | source |
| `ENGINE` | 805 × 22 | `sku`, `vertical`, `cat`, `perish`, `ads`, `position`, `rop`, `max`, `dos`, `state`, `price`, `inv_value`, `at_risk`, `expiry_u`, `order_units`, `order_value`, `vendor`, `brand`, `weekly_gmv`, `margin_rp`, `funding_rp`, `open_po` | `sku` (unique) | 17,600 | derived |
| `ENGINE_STORE` | 16,003 × 31 | `sku_id`, `store`, `vertical`, `cat`, `perish`, `seas`, `stockf`, `size`, `health`, `ads`, `on_hand`, `open_po`, `position`, `rop`, `max`, `dos`, `state`, `price`, `inv_value`, `at_risk`, `forecast_7d`, `order_sales`, `pack`, `order_buy`, `order_value`, `promo_incr_margin`, `at_risk_value`, `contribution_day`, `labour_fte`, `cluster`, `channel` | `sku_id + store` (unique) | 496,000 | derived |
| `A1 Demand Forecasting` | 13 × 7 | `vertical`, `forecast_7d`, `accuracy`, `trend`, `stockout_risk_skus`, `trending_skus`, `seasonality_idx` | `vertical` (unique) | 8 | reporting |
| `A2 Inventory Risk` | 13 × 7 | `vertical`, `stockout_risk_skus`, `overstock_skus`, `expiry_units`, `inventory_value`, `at_risk_value`, `avg_dos` | `vertical` (unique) | 40 | reporting |
| `A3 Replenishment` | 13 × 6 | `vertical`, `skus_to_reorder`, `order_units`, `order_value`, `fill_rate`, `avg_cover_d` | `vertical` (unique) | 24 | reporting |
| `Replenishment Detail` | 805 × 19 | `item`, `item_name`, `category`, `vertical`, `qty_on_hand`, `open_po`, `demand_day`, `rop`, `max`, `reorder`, `order_qty_sales`, `buy_uom`, `order_qty_buy`, `designated_vendor`, `unit_price_ta`, `amount`, `best_price_vendor`, `best_price`, `saving_vs_designated` | `item` (unique) | 15,200 | derived |
| `A4 Promotion` | 13 × 7 | `vertical`, `active_promo_skus`, `uplift`, `incremental_margin`, `roi_x`, `cannib`, `funding` | `vertical` (unique) | 8 | reporting |
| `Promotion & Discount Detail` | 53 × 18 | `promo_id`, `promo_name`, `discount_type`, `scope`, `vertical`, `target_category`, `season`, `peak_month`, `mechanism`, `discount`, `value_rule`, `min_qty_threshold`, `supplier_funding`, `expected_uplift`, `pre_buy_uplift_units`, `valid_from`, `valid_to`, `d365_construct` | `promo_id` (unique) | No | source |
| `A5 Pricing & Markdown` | 13 × 7 | `vertical`, `markdown_candidates`, `avg_depth`, `at_risk_state_value`, `recoverable`, `write_off`, `comp_idx` | `vertical` (unique) | 8 | reporting |
| `A6 Assortment` | 13 × 7 | `vertical`, `delist_candidates`, `grow_candidates`, `avg_gmroi`, `tail_share`, `capital_freed`, `contribution_day` | `vertical` (unique) | 8 | reporting |
| `A7 Workforce Optimizer` | 13 × 7 | `vertical`, `required_fte`, `scheduled_fte`, `coverage_gap`, `coverage`, `pt_positions`, `peak_shifts_wk` | `vertical` (unique) | 32 | reporting |
| `A8 Vendor & Brand` | 13 × 8 | `vertical`, `weekly_gmv`, `avg_otif`, `supplier_funding`, `top_vendor`, `vendors`, `brands`, layout column | `vertical` (unique) | 16 | reporting |
| `A9 AI Summary` | 13 × 7 | `vertical`, `inventory_at_risk`, `order_value`, `promo_incr_margin`, `markdown_recover`, `workforce_gap_fte`, `sales_at_risk_wf` | `vertical` (unique) | 32 | reporting |
| `Vendor Scorecard` | 13 × 12 | `vendor`, `skus`, `weekly_gmv`, `margin`, `otif`, `fill`, `lead_adh`, `funding`, `defect`, `score`, `at_risk_value`, layout column | `vendor` (unique) | 80 | derived |
| `Brand Performance` | 17 × 8 | `brand`, `skus`, `weekly_gmv`, `margin`, `growth`, `gmroi`, `share`, layout column | `brand` (unique) | 48 | derived |
| `Brand Events` | 28 × 4 | `store`, `vertical`, `event`, `demand_lift` | `store + event` (unique) | 23 | source |
| `Workforce` | 166 × 16 | `store`, `vertical`, `store_name`, `cluster`, `size`, `health`, `footfall_idx`, `event`, `event_lift`, `wf_base`, `peak`, `scheduled`, `required`, `gap`, `surplus`, `coverage` | `store` (unique, including aggregate `TOTAL`) | 1,604 | derived |
| `Vertical Rollup` | 14 × 12 | `vertical`, `stores`, `items`, `forecast_7d`, `inventory_value`, `at_risk_value`, `order_value`, `promo_incr_margin`, `recover_at_risk`, `contribution_day`, `wf_required`, `wf_gap` | `vertical` (unique) | 99 | reporting |
| `What-If Simulator` | 30 × 6 | `vertical`, `metric`, `baseline`, `live_levers`, two layout columns | `vertical + metric` (unique) | 48 | reporting |
| `What-If · Per Agent` | 13 × 5 | `vertical`, `forecast`, `at_risk`, `order`, `note` | `vertical` (unique) | No | reporting |
| `Command Center Charts` | 24 × 8 | repeated chart-label/value and layout columns | None | 14 | presentation |
| `A1 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A2 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A3 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A4 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A5 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A6 Charts` | 44 × 8 | repeated chart-label/value and layout columns | None | 26 | presentation |
| `A7 Charts` | 34 × 8 | repeated chart-label/value and layout columns | None | 20 | presentation |
| `A8 Charts` | 54 × 10 | repeated chart-label/value and layout columns | None | 36 | presentation |
| `UOM & PO Summary` | 13 × 6 | `vertical`, `order_value`, `order_qty_sales_units`, `order_qty_buy_units`, `avg_pack_factor`, `soa_note` | `vertical` (unique) | 32 | reporting |
| `Time Series 24mo` | 29 × 11 | `month`, `grc`, `gmr`, `fsh`, `hnb`, `elc`, `hnl`, `dgt`, `omn`, two empty columns | `month` (unique) | No | derived |
| `Formulas` | 24 × 3 | `metric`, `formula`, `notes` | `metric` (unique) | No | documentation |
| `Terminology` | 18 × 2 | `term`, `definition` | `term` (unique) | No | documentation |
| `Data Sources` | 15 × 4 | `source_object`, `system`, `refresh`, `consumed_by` | `source_object` (unique) | No | documentation |
| `D365 Table Reference` | 40 × 10 | row number, `business_entity_our_dataset`, `d365_f_o_table_aot_sql`, `layer`, `primary_key`, `related_to_join_field`, `key_fields_to_retrieve`, `module_enum_notes`, `conf`, layout column | Number for 33 data rows; final legend excluded | No | documentation |
| `D365 Field Mapping` | 339 × 6 | `dataset_column`, `d365_table`, `d365_field`, `retrieval`, `integration_logic_transform_10_0_48`, `conf` | Section + dataset-column grain; no global row key claimed | No | documentation |
| `D365 Worked Example` | 35 × 8 | step number, `what_we_need`, `d365_source_table_field`, `query_filter_10_0_48`, `logic_transform`, `value_grc_092`, `conf`, layout column | Step number within worked example; explanatory lines also present | No | documentation |
| `ERP Approval Matrix` | 9 × 4 | `flow`, `tier_1`, `tier_2`, `tier_3` | `flow` (unique) | No | documentation |
| `Agentic Prompts` | 14 × 5 | `agent`, `role`, `trigger`, `output`, `guardrail` | `agent` (unique) | No | documentation |
| `Demo Script` | 16 × 3 | `step`, `talk_track`, `show` | `step` (unique) | No | presentation |

Proven value relationships: Stores/Category/SKU → Vertical; SKU → Category; Trade Agreement → SKU/Vendor; ENGINE → SKU; ENGINE_STORE → SKU/Store; Brand Events → Store; Workforce → Store after explicitly excluding its `TOTAL` aggregate; Replenishment Detail → SKU. All 12 relationship checks pass after that documented aggregate exclusion.

## 4. Sheet Classification

Every sheet has exactly one primary classification. Counts: `STRUCTURED` 1, `SEMANTIC` 9, `BOTH` 8, `DERIVED` 20, `IGNORE` 11.

- `STRUCTURED`: `Trade Agreement`—high-volume exact commercial facts.
- `SEMANTIC`: `Cover & Storyline`, `Formulas`, `Terminology`, `Data Sources`, `D365 Table Reference`, `D365 Field Mapping`, `D365 Worked Example`, `ERP Approval Matrix`, `Agentic Prompts`—narrative, business-rule, integration, governance, or operating knowledge.
- `BOTH`: `Constants`, `Verticals`, `Stores`, `Categories`, `Main Vendor`, `SKU_Master`, `Promotion & Discount Detail`, `Brand Events`—exact relational attributes plus meaningful retrieval context.
- `DERIVED`: `ENGINE`, `ENGINE_STORE`, all A1–A9 summary tabs, `Replenishment Detail`, `Vendor Scorecard`, `Brand Performance`, `Workforce`, `Vertical Rollup`, both What-If tabs, `UOM & PO Summary`, and `Time Series 24mo`—calculated snapshots or reports. Only selected useful exact grains are loaded; they are not treated as independent source masters.
- `IGNORE`: `LISTING`, `Command Center Charts`, `A1 Charts` through `A8 Charts`, and `Demo Script`—navigation/presentation artifacts or duplicated chart backing ranges. `Demo Script` is presales presentation content rather than production business knowledge.

The row-by-row reason is encoded in `classification.py` and copied into `generated/workbook_inventory.json`; no worksheet is silently skipped.

## 5. Proposed Relational Schema

The preflight catalog check found no `retail` schema and zero `retail` tables. `sql/retail/001_create_retail_schema.sql` created the following additive schema. Every business table has required lineage columns `source_load_id BIGINT` (FK to `SourceLoad`), `source_sheet NVARCHAR(128)`, `source_row INT`, and `loaded_at DATETIME2(3)`. Below, `?` means nullable; fields without `?` are `NOT NULL`.

### `retail.SourceLoad`

- Purpose/source: one idempotency and lineage record per source workbook hash; Excel now, replaceable adapter later.
- PK: `source_load_id BIGINT IDENTITY`; unique `workbook_sha256 CHAR(64)`.
- Columns: `workbook_name NVARCHAR(260)`, `workbook_sha256 CHAR(64)`, `source_type NVARCHAR(30)`, `load_status NVARCHAR(20)`, `loaded_at DATETIME2(3)`, `completed_at DATETIME2(3)?`, `row_count INT?`.
- Rules: status check allows only `STARTED`, `COMPLETED`, `FAILED`; rerunning the same hash reuses the row and updates it rather than inserting another load.

### `retail.LegalEntity`

- Purpose/source: normalized vertical/legal-entity master from `Verticals`.
- PK/FKs: `legal_entity_id NVARCHAR(10)`; unique name; lineage FK.
- Columns: `legal_entity_name NVARCHAR(200)`, `short_name NVARCHAR(100)`, `workforce_base_per_size DECIMAL(18,6)?`, `sales_per_fte DECIMAL(28,4)?`, `peak_season_factor DECIMAL(18,6)?`, `total_store_size DECIMAL(18,6)?`.
- Transform: preserve the workbook ID as the business key; no surrogate entity relationship.

### `retail.Store`

- Purpose/source: store master from `Stores`.
- PK/FKs: `store_id NVARCHAR(20)`; `legal_entity_id` → `LegalEntity` (value-validated).
- Columns: `store_name NVARCHAR(240)`, `cluster NVARCHAR(80)?`, `size_factor DECIMAL(18,6)?`, `health_factor DECIMAL(18,6)?`, `footfall_index DECIMAL(18,6)?`, `channel NVARCHAR(80)?`.
- Indexes/rules: indexes on legal entity and channel; values retained as model factors, not reinterpreted as physical area or health scores.

### `retail.Category`

- Purpose/source: entity-scoped category master from `Categories`.
- PK/FKs: `category_id NVARCHAR(20)`; `legal_entity_id` → `LegalEntity`; unique `(legal_entity_id, category_name)`.
- Columns: `category_name NVARCHAR(200)`, `is_perishable BIT`.
- Index/rules: entity index; `Y/N` becomes `BIT`.

### `retail.Vendor`

- Purpose/source: supplier master from `Main Vendor`.
- PK: `vendor_account NVARCHAR(20)`; unique `vendor_code NVARCHAR(80)`.
- Columns: `vendor_name NVARCHAR(240)`, `vendor_group NVARCHAR(80)?`, `currency NVARCHAR(10)?`, `payment_terms NVARCHAR(60)?`, `delivery_terms NVARCHAR(60)?`, `lead_time_days INT?`, `moq_units DECIMAL(28,6)?`, `otif_pct`, `fill_pct`, `defect_pct`, `lead_adherence_pct` as `DECIMAL(9,4)?`.
- Transform: workbook `Vendor A`…`Vendor H` is retained as `vendor_code`; `V0001`…`V0008` is the FK business key.

### `retail.Brand`

- Purpose/source: normalized distinct brand master derived from `SKU_Master` because the workbook has no separate brand master.
- PK: `brand_name NVARCHAR(160)`.
- Columns/rules: lineage points to the first SKU source row for the brand; no invented brand ID or description.

### `retail.Sku`

- Purpose/source: SKU/product master from `SKU_Master`.
- PK/FKs: `sku_id NVARCHAR(30)`; entity, category, vendor, brand, and lineage FKs—all source-value validated.
- Columns: `item_name NVARCHAR(240)`, `is_perishable BIT`, `base_ads DECIMAL(28,8)?`, `price DECIMAL(28,4)?`, `margin_pct DECIMAL(18,8)?`, `cost DECIMAL(28,4)?`, `lead_time_days INT?`, `on_hand_days DECIMAL(18,6)?`, `open_po_units DECIMAL(28,6)?`, `safety_days DECIMAL(18,6)?`, `expiry_days DECIMAL(18,6)?`, `growth_factor`, `elasticity`, `funding_pct`, `cannibalization_pct`, `seasonality_factor`, `stock_factor` as `DECIMAL(18,8)?`, `competitor_index DECIMAL(18,6)?`, `is_promo BIT`, `is_viral BIT`, `sales_uom NVARCHAR(40)?`, `buy_uom NVARCHAR(40)?`, `pack_factor DECIMAL(18,6)?`, `channel NVARCHAR(80)?`, `sales_per_fte DECIMAL(28,4)?`, `vendor_account NVARCHAR(20)?`, `brand_name NVARCHAR(160)?`.
- Indexes/rules: entity/category, vendor, and brand indexes; `Y/N` flags become `BIT`; vendor label is deterministically resolved through `Main Vendor.vendor` to its account.

### `retail.TradeAgreement`

- Purpose/source: item-vendor pricing facts from `Trade Agreement`.
- PK/FKs: `(sku_id, vendor_account, valid_from, min_quantity)`; SKU/vendor/lineage FKs.
- Columns: `item_name NVARCHAR(240)`, `unit_price DECIMAL(28,4)`, `currency NVARCHAR(10)`, `lead_time_days INT?`, `discount_pct DECIMAL(18,8)?`, `valid_to DATE?`, `is_designated BIT`.
- Indexes/rules: vendor index and `(sku_id, is_designated)` index; ISO date text is explicitly parsed to `DATE`; no price rounding beyond the declared SQL scale.

### `retail.Promotion`

- Purpose/source: promotion definitions from `Promotion & Discount Detail`.
- PK/FKs: `promotion_id NVARCHAR(30)`; legal entity and lineage FKs.
- Columns: name/type as `NVARCHAR(240/120)`, `scope NVARCHAR(40)?`, `target_category NVARCHAR(200)?`, `season NVARCHAR(160)?`, `peak_month NVARCHAR(30)?`, `mechanism NVARCHAR(300)?`, `discount_pct DECIMAL(18,8)?`, `value_rule NVARCHAR(160)?`, `min_quantity_threshold NVARCHAR(100)?`, `supplier_funding_pct`, `expected_uplift_pct` as `DECIMAL(18,8)?`, `prebuy_uplift_units DECIMAL(28,6)?`, `valid_from DATE?`, `valid_to DATE?`, `d365_construct NVARCHAR(500)?`.
- Indexes/rules: entity/date index; nine percentage fields are intentionally null for fixed-amount/deal mechanisms; workbook vertical labels use an explicit documented alias map to the eight actual entity IDs.

### `retail.InventorySnapshot`

- Purpose/source: current chain-per-SKU calculated inventory state from `ENGINE`.
- PK/FKs: `sku_id`; SKU and lineage FKs.
- Columns: `ads DECIMAL(28,8)?`, position/ROP/max/expiry/order/open-PO quantities as `DECIMAL(28,6)?`, `days_of_supply DECIMAL(28,8)?`, `inventory_state NVARCHAR(40)?`, price/value/GMV/margin/funding amounts as `DECIMAL(28,4)?`.
- Index/rules: state index; one current snapshot per SKU because the workbook supplies no as-of timestamp. The source load provides version lineage.

### `retail.StoreSkuSnapshot`

- Purpose/source: exact store × SKU facts from `ENGINE_STORE`; deliberately not emitted as 16,000 repetitive semantic documents.
- PK/FKs: `(sku_id, store_id)`; SKU, Store, and lineage FKs.
- Columns: ADS/DoS/forecast/labour as `DECIMAL(28,8)?`; on-hand/open-PO/position/ROP/max/order quantities as `DECIMAL(28,6)?`; `inventory_state NVARCHAR(40)?`; price/value/promo-margin/contribution fields as `DECIMAL(28,4)?`; `pack_factor DECIMAL(18,6)?`.
- Indexes/rules: `(store_id, inventory_state)` and state indexes. Workbook formula results are loaded; formulas themselves remain inspectable in the inventory report.

### `retail.ReplenishmentProposal`

- Purpose/source: SKU-level derived requisition and vendor comparison from `Replenishment Detail`.
- PK/FKs: `sku_id`; SKU, designated vendor, best-price vendor, and lineage FKs.
- Columns: `reorder_required BIT`, sales/buy quantities `DECIMAL(28,6)?`, `buy_uom NVARCHAR(40)?`, unit price/amount/best price/saving `DECIMAL(28,4)?`.
- Index/rules: reorder flag index; `YES/—` becomes `BIT`; vendor labels resolve only through validated vendor codes.

### `retail.BrandEvent`

- Purpose/source: store-event facts from `Brand Events`.
- PK/FKs: `(store_id, event_name)`; Store, LegalEntity, and lineage FKs.
- Columns: `event_name NVARCHAR(240)`, `legal_entity_id NVARCHAR(10)`, `demand_lift DECIMAL(18,8)?`.
- Transform: workbook event values are preserved; no event date is invented because none is supplied.

### `retail.WorkforceSnapshot`

- Purpose/source: calculated store staffing state from `Workforce`.
- PK/FKs: `store_id`; Store and lineage FKs.
- Columns: `event_name NVARCHAR(240)?`, event/peak factors `DECIMAL(18,8)?`, base `DECIMAL(18,6)?`, scheduled/required/gap/surplus FTE `DECIMAL(28,6)?`, `coverage_pct DECIMAL(18,6)?`.
- Transform: aggregate row `TOTAL` is explicitly excluded from the store-keyed table; 137 stores legitimately have no event name.

### `retail.MonthlySales`

- Purpose/source: normalize the wide `Time Series 24mo` sheet to entity/period facts.
- PK/FKs: `(period_label, legal_entity_id)`; LegalEntity and lineage FKs.
- Columns: `period_label NVARCHAR(20)`, `sales_amount DECIMAL(28,4)`.
- Index/rules: entity/period index; labels such as `Jan-Y1` are preserved because the workbook does not supply calendar years/dates.

The loader is upsert-only: it inserts new business keys and updates matching keys, never deletes records absent from a later source. It uses source-neutral normalized dictionaries; the Excel adapter is the only layer aware of rows/headers. Temporary bounded-text staging works around `mssql-python` bulk DECIMAL binding defects, while Azure SQL performs and enforces conversion into the strongly typed final tables. A real rerun kept every count unchanged.

## 6. Proposed Semantic Document Types

All builders emit `doc_key`, `doc_type`, `source_sheet`, `source_key`, `content`, structured `metadata`, and SHA-256 `content_hash`. Counts below are the actual full-corpus counts.

| `doc_type` | Source(s), grain, and joins | Content and metadata | Intentionally excluded | Count |
|---|---|---|---|---:|
| `vertical` | `Verticals`; one per entity | Name/code, workforce and seasonality context; metadata entity/name | Store/SKU rollups | 8 |
| `store` | `Stores` + matching `Brand Events`/`Workforce`; one per store | Location label, entity, cluster, channel, factors, event/staffing context; filter metadata | Store×SKU numerical grid | 160 |
| `category` | `Categories` + SKU count; one per category ID | Entity, category, perishability, SKU count | Inventory measures | 160 |
| `vendor` | `Main Vendor` + main-vendor SKU count; one per account | Commercial/service context; metadata account/group/currency | Full trade-price rows and derived scorecard values | 8 |
| `brand` | distinct `SKU_Master.brand`; one per brand | Workbook occurrence and SKU count; metadata brand | Invented descriptions and volatile performance prose | 12 |
| `sku` | `SKU_Master` + Vertical + Category + Vendor + Trade Agreement + chain `ENGINE`; one per SKU | Product identity/context, UOM, lead/safety, inventory state, designated agreement summary; rich filter metadata | All store×SKU rows and noisy derived financial measures | 800 |
| `promotion` | `Promotion & Discount Detail` + entity map; one per promotion ID | Mechanism, target, funding/uplift, validity, D365 construct | Repetition of every numerical engine impact | 48 |
| `brand_event` | `Brand Events` + Store; one per store/event pair | Event, store/entity, demand lift | Invented event dates | 23 |
| `workbook_overview` | `Cover & Storyline`; one workbook narrative | Dataset scope/use | Layout cells | 1 |
| `model_parameter` | `Constants`; one per named value, excluding the section header | Parameter/value; structured value metadata | Empty layout cells | 12 |
| `formula` | `Formulas`; one per metric | Formula and notes | Raw Excel formula cells from calculation tabs | 19 |
| `terminology` | `Terminology`; one per term | Definition | None beyond layout | 13 |
| `data_source` | `Data Sources`; one per source object | System, refresh, consumers | No credentials/endpoints | 10 |
| `d365_table` | `D365 Table Reference`; one per numbered mapping | Table, keys, joins, fields, notes, confidence | Legend row | 33 |
| `d365_field_mapping` | `D365 Field Mapping`; one per workbook dataset section, grouping its field rows | Field/table/retrieval/transform/confidence lines; section metadata | Hundreds of tiny row documents | 29 |
| `d365_worked_example` | `D365 Worked Example`; one complete GRC-092 trace | Worked steps, queries, calculations, confidence | Nothing factual; kept as one coherent trace | 1 |
| `approval_rule` | `ERP Approval Matrix`; one per flow | Three approval tiers | No invented workflow status | 4 |
| `agent_spec` | `Agentic Prompts`; one per agent | Role, trigger, output, guardrail | No prompt expansion or frontend integration | 9 |

Expected and actual total: **1,350 documents**. Example SKU document:

> SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail (Hypermarket) (GRC). It is perishable, branded Brava, with main vendor Everest Wholesale (V0005). It sells in Bottle and is bought in Crate with pack factor 12; workbook lead time is 2 days and safety coverage is 1 day. Current chain inventory state is Low: position 1176, reorder point 1491, and proposed order units 2302. Its designated trade agreement is with Everest Wholesale at 14300 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreements are recorded.

### Representative 10-document review sample

The exact JSON objects are in `generated/retail_documents_sample.jsonl`. The reviewed content set is:

1. `sku:dgt-001` — Digital Electronics 1; Low; Boreas Trading; Carton/24; position 5684 vs ROP 5813; two alternate agreements.
2. `sku:elc-001` — Smartphones 1; Healthy; Garuda Distribution; Case/3; position 611 vs ROP 582.
3. `sku:fsh-001` — Men's Apparel 1; Low; Everest Wholesale; Pack/6; position 2661 vs ROP 2745.
4. `sku:gmr-001` — Menswear 1; Healthy; Cendana Distribusi; Box/4; position 727 vs ROP 639.
5. `sku:grc-001` — Fruit 1; perishable/Low; Everest Wholesale; Crate/12; position 1176 vs ROP 1491.
6. `vendor:v0001` — Aurora Supply Co, terms/service metrics, and 116 main-vendor SKUs.
7. `brand:altura` — 67 assigned SKUs; no invented brand narrative.
8. `formula:ads-per-store` — `base × seasonality(vertical,month) × store size × (1+demand lever)`.
9. `terminology:ads` — Average Daily Sales definition.
10. `d365-field-mapping:a1-demand-forecasting-per-vertical-aggregated-from-engine-store-forecastsales` — grouped seven-row A1 mapping across legal entity, forecast, accuracy, trend, risk, trending, and seasonality fields.

Review result: factual joins and traceability passed; content is concise; store×SKU noise is excluded; the sample spans five legal entities; no invented description was found. Programmatic sample validation: 10/10 valid, 10 unique keys, zero errors/warnings.

## 7. Decisions and Assumptions

- The workbook, rather than the illustrative entity list in the task, is the source of truth.
- Existing PostgreSQL application schemas and models remain untouched. The new foundation uses the already validated Azure SQL connection in `backend/.env` through `AZURE_SQL_CONNECTIONSTRING`.
- No credentials or connection-string details will be written to generated reports, logs, tests, SQL scripts, or console output.
- No embeddings, embedding API calls, `ai.*` vector table, vector index, or retrieval integration are part of this phase.
- Existing repository changes in `.gitignore`, `backend/.env.example`, and the untracked `scripts/test_db.py` predate this work and will be preserved.
- `ENGINE_STORE` is structured only. It contributes exact SQL facts but generates zero semantic documents, avoiding 16,000 repetitive texts.
- The chain `ENGINE`, workforce, replenishment, and monthly series are loaded as current derived snapshots/facts because they support exact queries. Their reporting summary tabs are not duplicated as SQL tables.
- `SKU_Master.vendor` contains labels (`Vendor A`…`Vendor H`), while relational FKs use `Main Vendor.vendor_account`; the unique `Main Vendor.vendor` values prove the mapping.
- The promotion sheet uses display labels that do not exactly equal all entity names. The explicit map is: Grocery→GRC, General Merch→GMR, Fashion→FSH, Health & Beauty→HNB, Electronics→ELC, Home & Living→HNL, Digital/Online→DGT, Omnichannel→OMN. This is recorded rather than inferred dynamically.
- Brands have no standalone master sheet; the normalized Brand table uses the 12 distinct non-null `SKU_Master.brand` values and points lineage to each brand's first SKU row. No arbitrary brand identifier is created.
- Percent conventions are preserved as supplied: SKU margin/funding/cannibalization values are fractional ratios, while vendor service and promotion percentage fields are percentage-point values. No silent cross-field rescaling occurs.
- Workbook date cells in agreements/promotions are ISO strings; the Excel adapter explicitly parses them as dates before normalized loading.
- `Time Series 24mo` supplies relative labels (`Jan-Y1`…`Dec-Y2`) rather than calendar dates, so `period_label` is text. No year is invented.
- `ENGINE` and `ENGINE_STORE` have no snapshot/as-of timestamp. `SourceLoad` hash/time provides source version lineage; consumers must not treat it as an independently observed business date.
- The `Workforce` `TOTAL` row is an aggregate, not a store; it is explicitly excluded from `WorkforceSnapshot`. The 160 store rows reconcile to the Store master.
- Nine promotions legitimately lack `discount_pct` because their mechanisms use fixed amount or deal-price rules in `value_rule`.
- A later workbook missing a previously loaded business key will not cause deletion. The loader is deliberately insert/update only until authoritative deletion semantics are confirmed for D365/ERP.
- The existing Formula Manager JSON remains separate. Workbook formula definitions become semantic documents but are not copied into the Formula Manager store or a new SQL formula table.
- Temporary `NVARCHAR` staging is an Azure SQL driver interoperability measure only. Final tables remain strongly typed, and the database performs conversions under one transaction before constraints are accepted.
- D365 `[M]`, `[L]`, and computed `[C]` mappings remain workbook claims and require implementation-specific validation; they are not upgraded to verified `[H]` claims.

## 8. Progress Log

### 2026-08-12 UTC — Repository discovery started

- Work completed: inspected the repository root, located the workbook, existing backend configuration/database modules, dependency file, Excel viewer, repository instructions, and existing Azure SQL readiness script.
- Files created/changed: created this plan/log only.
- Commands/tests run: repository file inventory, `git status --short`, `.gitignore` inspection, `git check-ignore -v backend/.env`, and read-only source inspection.
- Results: workbook located under `resources/`; `backend/.env` is ignored by Git; Azure SQL uses `AZURE_SQL_CONNECTIONSTRING` in the existing readiness script; the application also has separate PostgreSQL SQLAlchemy models that must not be conflated with this Azure SQL foundation.
- Blockers: none. Workbook profiling and Azure SQL catalog inspection remain pending.

### 2026-08-12 03:37–03:49 UTC — Inspection and normalization implemented

- Work completed: added the `src.retail_data_bootstrap` CLI/package, strict classification map, Excel source adapter, machine-readable inspector, source-neutral normalization, and dry-run structured pipeline.
- Files created/changed: bootstrap package modules, `.gitignore`, `backend/requirements.txt`, this log.
- Commands/tests run: `inspect-workbook`; `ingest-structured --dry-run`; direct read-only workbook probes.
- Results: all 49 sheets inventoried/classified; 12 relationship candidates checked; 14 normalized business tables and 21,571 rows produced; dry-run opened no database connection.
- Blockers: raw Workforce relationship initially showed one non-store value, `TOTAL`; identified and documented as an aggregate exclusion.

### 2026-08-12 03:49–03:56 UTC — SQL design and semantic sample implemented

- Work completed: added additive Azure SQL migration, catalog conflict preflight, transactional staging/upsert loader, semantic builders, content hashing, secret/duplicate/size validation, and JSONL writer.
- Files created/changed: `sql/retail/001_create_retail_schema.sql`, database/document/validation modules, CLI commands, generated inventory/sample/full corpus.
- Commands/tests run: `generate-documents --sample-only`, manual JSONL sample read, `generate-documents`.
- Results: representative 10-document sample passed; full 1,350-document corpus passed with deterministic unique keys and hashes.
- Blockers: initial Azure SQL catalog calls timed out; no change was made. A later approved retry succeeded.

### 2026-08-12 03:57–04:04 UTC — Azure SQL migration and ingestion

- Work completed: inspected live catalog, applied migration, diagnosed driver bulk-binding failures, made ISO-date normalization explicit, switched only temporary staging to bounded text, loaded data, and verified source/live counts.
- Files created/changed: database binding/staging logic and date transformation.
- Commands/tests run: `inspect-database`; `migrate`; repeated transactional `ingest-structured`; `validate --live`.
- Results: preflight found zero existing `retail` objects; migration created 15 tables in 16 batches. Failed load attempts rolled back completely. Final load committed 21,571 rows; 33 FKs are enabled/trusted; all 15 tables have PKs; SourceLoad is `COMPLETED`.
- Blockers: `mssql-python 1.13.0` could not reliably bulk-bind Python floats/DECIMAL values and emitted opaque truncation errors. Resolved with bounded-text temporary staging and Azure SQL typed conversion into final tables.

### 2026-08-12 04:04–04:08 UTC — Idempotence, tests, and final validation

- Work completed: reran the real loader, regenerated current inventory/sample/full JSONL, added pure and opt-in live tests, and completed this handoff.
- Files created/changed: `backend/tests/test_retail_data_bootstrap.py`, `backend/pytest.ini`, finalized bootstrap files and log.
- Commands/tests run: second `ingest-structured`; `python -m pytest -q tests/test_retail_data_bootstrap.py`; `python -m pytest -q tests`; final `inspect-workbook`, `generate-documents`, and `validate`.
- Results: idempotent rerun reused SourceLoad and left every business-table count unchanged; new tests 14 passed/1 live skipped; full backend test directory 265 passed/1 live skipped; final inventory relationships 12/12; JSONL 1,350/1,350 valid.
- Blockers: bare repository-wide `python -m pytest -q` also collects the pre-existing executable `backend/test_retail_tool.py`, which immediately requires `D365_RESOURCE` and fails during collection. The maintained `backend/tests/` suite passes; that unrelated script was not changed.

### 2026-08-12 04:09–04:14 UTC — Completion checks

- Work completed: ran compile checks, executed the opt-in live Azure test, reran the additive migration, and reinspected the live catalog.
- Files created/changed: no new implementation scope; finalized tests and this log.
- Commands/tests run: `compileall`; both test suites; live `-m azure_sql`; `migrate`; `inspect-database`; `git diff --check`.
- Results: compile clean; live test 1 passed; migration rerun was a no-op-safe success; catalog remains exactly 15 `retail` tables; diff check clean.
- Blockers: none for phase review.

### 2026-08-12 06:27 UTC — Phase 4.5 semantic audit started

- Work completed: read this persistent plan completely; inspected all semantic builders, the document model, validation, CLI generation path, unit tests, the 10-document sample, and all 1,350 current JSONL objects.
- Files created/changed: this log entry only; the pre-hardening sample was retained in session for exact comparison.
- Commands/tests run: source inspection; corpus grouping by `doc_type`; top-level/metadata-key inventory; exact sample content/hash capture.
- Results: all 18 document types are accounted for. Confirmed operational leakage in SKU, Store, Vendor, Category, Brand, Vertical, Promotion, Brand Event, and volatile What-If model-parameter content. The existing hash function already hashes canonical content only, but lacks explicit regression coverage.
- Blockers: none. No SQL migration, ingestion, or live database mutation is required or authorized for Phase 4.5.

### 2026-08-12 06:28–06:32 UTC — Semantic contract and representative sample hardened

- Work completed: added the controlled retrieval-domain contract; made `retrieval_domain` a required top-level field; removed volatile snapshot, performance, forecast, price, staffing, derived-count, and adjustable-lever values from semantic content/metadata; extended deterministic and leakage validation; added regression coverage; regenerated and reviewed the same 10 sample identities.
- Files created/changed: `backend/src/retail_data_bootstrap/semantic_contract.py`, `models.py`, `documents.py`, `validation.py`, `backend/tests/test_retail_data_bootstrap.py`, `generated/retail_documents_sample.jsonl`, and this log.
- Commands/tests run: `generate-documents --sample-only`; exact old/new sample comparison; focused `python -m pytest -q tests/test_retail_data_bootstrap.py`.
- Results: sample validation passed 10/10. Five SKU documents, one vendor, and one brand changed; formula, terminology, and D365 mapping semantic content/hashes stayed identical. Focused bootstrap tests passed 23 with one opt-in live-Azure test skipped.
- Blockers: none. No Azure SQL command was run and no relational source/model mapping changed.

### 2026-08-12 06:33–06:36 UTC — Full hardening corpus and final verification

- Work completed: regenerated the complete corpus, ran independent relational/JSONL validation, compiled the changed package/tests, ran the maintained backend suite, reconciled counts/domains, and finalized the Phase 4.5 audit and freeze recommendation.
- Files created/changed: `generated/retail_documents.jsonl` and this log; no SQL, frontend, endpoint, agent, or vector-layer file changed.
- Commands/tests run: `generate-documents`; `validate`; `python -m compileall -q src/retail_data_bootstrap tests/test_retail_data_bootstrap.py`; `python -m pytest -q tests`; working-tree/diff checks.
- Results: 1,350/1,350 documents valid, 18/18 types mapped to exactly one of eight domains, no key/count changes, all hashes match semantic content, and the backend suite passed 274 tests with one live-Azure test skipped. The sole warning is the retained, factual 37-character `terminology:dos` document.
- Blockers: none. Phase 4.5 is ready for human review; Phase 5 has not started.

## 9. Validation Results

### Workbook

- 49/49 sheets inspected and exactly classified.
- Formula presence counted from the formula workbook; cached displayed values read separately. Major formula grids: `ENGINE` 17,600; `ENGINE_STORE` 496,000; `Replenishment Detail` 15,200.
- Declared candidate keys are unique. No duplicate normalized primary key was found.
- 12/12 proposed source relationships validate by actual values after the explicit Workforce `TOTAL` aggregate exclusion.
- Machine-readable report: `generated/workbook_inventory.json`.

### Relational source and Azure SQL

| Table | Source rows | Live rows |
|---|---:|---:|
| `retail.LegalEntity` | 8 | 8 |
| `retail.Store` | 160 | 160 |
| `retail.Category` | 160 | 160 |
| `retail.Vendor` | 8 | 8 |
| `retail.Brand` | 12 | 12 |
| `retail.Sku` | 800 | 800 |
| `retail.TradeAgreement` | 2,400 | 2,400 |
| `retail.Promotion` | 48 | 48 |
| `retail.InventorySnapshot` | 800 | 800 |
| `retail.StoreSkuSnapshot` | 16,000 | 16,000 |
| `retail.ReplenishmentProposal` | 800 | 800 |
| `retail.BrandEvent` | 23 | 23 |
| `retail.WorkforceSnapshot` | 160 | 160 |
| `retail.MonthlySales` | 192 | 192 |
| **Total business rows** | **21,571** | **21,571** |

- Source primary-key duplicates: 0. Source FK violations: 0. Live count mismatches: 0.
- Live schema: 15 tables including SourceLoad; 15 PK-bearing tables; 33 FKs, all enabled and trusted.
- SourceLoad: `COMPLETED`, recorded row count 21,571. Real rerun left every count unchanged.
- Null/quality findings: `Promotion.discount_pct` 9 intentional nulls for non-percent mechanisms; `WorkforceSnapshot.event_name` 137 nulls because most stores have no event. No other normalized nulls.
- No destructive SQL was run. No existing object was dropped/replaced. No vector column/table/index exists in this migration.

### Semantic/JSONL

| Type | Count | Type | Count |
|---|---:|---|---:|
| `sku` | 800 | `store` | 160 |
| `category` | 160 | `promotion` | 48 |
| `d365_table` | 33 | `d365_field_mapping` | 29 |
| `brand_event` | 23 | `formula` | 19 |
| `terminology` | 13 | `brand` | 12 |
| `model_parameter` | 12 | `data_source` | 10 |
| `agent_spec` | 9 | `vendor` | 8 |
| `vertical` | 8 | `approval_rule` | 4 |
| `d365_worked_example` | 1 | `workbook_overview` | 1 |

- Total: 1,350; unique keys: 1,350; duplicate source identities: 0; duplicate same-type content: 0.
- Hashes: all 1,350 are lowercase 64-hex SHA-256 and match canonical content; deterministic regeneration passed.
- Metadata: all JSON serializable with no NaN; source sheet/key/row trace present.
- Secret scan: 0 suspected credential/connection contents.
- Content size after hardening: 37–4,139 characters, average 368.53. One warning: `terminology:dos` is a factual but short 37-character definition.
- JSONL: 1,350 valid object lines; no `embedding` or `vector` field; file is `generated/retail_documents.jsonl`.

### Automated tests

- Bootstrap tests after Phase 4.5: **23 passed, 1 skipped** (live Azure marker opt-in).
- Complete maintained `backend/tests/` suite after Phase 4.5: **274 passed, 1 skipped**.
- Repository-root backend pytest collection caveat: pre-existing `backend/test_retail_tool.py` performs a D365 call at import and fails without `D365_RESOURCE`; it is not part of the maintained `backend/tests/` suite.

## 10. Open Questions / Blockers

- Confirm whether workbook “Vertical / Legal Entity” archetypes should map 1:1 to production D365 `DataAreaId` companies; the workbook uses both legal-entity and retail-archetype language.
- Confirm the production business date/as-of timestamp and snapshot retention policy for `InventorySnapshot`, `StoreSkuSnapshot`, `WorkforceSnapshot`, and `ReplenishmentProposal` before incremental D365 loads. Today only source-load lineage is available.
- Confirm deletion/inactivation semantics when an entity disappears from a later D365 extract. Current upsert behavior intentionally never deletes.
- Confirm whether category names are entity-scoped as modeled or should eventually reference a cross-entity category hierarchy.
- Validate D365 mappings marked `[M]`, `[L]`, or computed `[C]` against the client's 10.0.48 data dictionary/configuration before connector implementation.
- Confirm whether workbook ratios (`margin`, `fund`, `cannib`) and percentage-point fields should be normalized to one consistent storage convention in a future contract. This phase preserves source conventions to avoid changing meaning.
- Confirm whether Brand should gain an enterprise key/master from D365; the workbook only supports brand name as a natural key.
- No technical blocker remains for review of this phase.

Ready for the next phase after human review: freeze the accepted document contracts and relational schema, then create a separate versioned migration for an `ai` document/vector table and an embedding pipeline that reads `generated/retail_documents.jsonl`, embeds only changed `content_hash` values, upserts transactionally, and validates vector dimensions/counts. Do not begin that work until this plan and sample corpus are approved.

## Phase 4.5 — Semantic Contract Hardening

### Objective

Freeze a semantic contract that represents stable business knowledge rather than duplicating the operational snapshot layer. Phase 4.5 adds deterministic top-level retrieval routing, removes volatile current-state facts from embedding content and unnecessary metadata, proves that `content_hash` depends only on canonical semantic content, regenerates both corpora, and leaves all validated `retail.*` objects and rows unchanged.

### Initial audit findings

- `sku` content embeds current inventory state, position, reorder point, proposed order units, and exact trade-agreement price. `inventory_state` is also copied into metadata and `ENGINE` is listed as a semantic source.
- `store` content embeds mutable size/health/footfall factors and current scheduled/required FTE; it lists Workforce as a semantic source even though staffing belongs in `retail.WorkforceSnapshot`.
- `vendor` content embeds current OTIF, fill, defect, and lead-adherence measurements plus a derived current SKU count.
- `vertical`, `category`, and `brand` include model/derived counts or KPI-like values that can change without changing entity meaning.
- `promotion` mixes definition/configuration with expected uplift, a forecast rather than durable policy.
- `brand_event` mixes event identity/context with calculated demand lift.
- six What-If `model_parameter` documents embed the current lever value even though those values are intentionally adjustable.
- formula, terminology, data-source, D365, approval, agent, and workbook-documentation builders are naturally semantic. Their existing grouping removes layout cells; the D365 worked example is explicitly illustrative integration knowledge rather than a live snapshot.
- The existing `content_hash` implementation is SHA-256 of whitespace-canonicalized `content` only. It is already independent of metadata and timestamps, but this behavior was implicit and not fully regression-tested.

### Semantic field-classification rules

- **STABLE_SEMANTIC** — identity, names, business membership/meaning, perishability, brand/vendor association, UOM/pack relationships, definitions, formulas, D365 mappings, governance, and agent responsibilities. These belong in `content` and therefore affect `content_hash`.
- **FILTERABLE_METADATA** — stable IDs and low-cardinality routing/filter fields (`sku_id`, `store_id`, `vendor_account`, `legal_entity_id`, category, brand, channel), plus source-row traceability. These do not affect `content_hash`.
- **VOLATILE_OPERATIONAL** — current inventory/ROP/DoS/state/order/price/value/forecast/staffing/performance/impact values and mutable population counts. These remain in `retail.*` and are excluded from semantic content; they are not copied into metadata merely because they exist.
- **CONTRACTUAL_OR_SLOWLY_CHANGING** — UOM, pack factor, vendor relationship, payment/delivery terms, lead time, MOQ, agreement existence, promotion mechanism/rule/validity, and fixed calculation parameters. These may remain in semantic content because a change alters business meaning/configuration and should trigger re-embedding.

### Complete semantic-field audit

The labels below classify every source value that contributes to the final contract. `A` = **STABLE_SEMANTIC**, `B` = **FILTERABLE_METADATA**, `C` = **VOLATILE_OPERATIONAL**, and `D` = **CONTRACTUAL_OR_SLOWLY_CHANGING**. Fields marked `C removed` were inputs to the prior builder and are no longer used in semantic content/metadata.

Common to every type:

- `doc_key` is deterministically derived as `slug(doc_type):slug(source_key)`. `doc_type` and the source entity/business key are `A`; the key is identity, not prose.
- `source_key` is the actual source entity/business key (`A` and `B`); `source_sheet` and metadata source row(s) are traceability (`B`).
- top-level `retrieval_domain` is deterministic routing/filter data (`B`) derived only from `doc_type`.
- `content_hash` is an output contract field: lowercase SHA-256 of canonical semantic `content` only. It does not hash any top-level identifier, domain, metadata, row number, timestamp, or source-load ID.

| `doc_type` | Semantic content (`A` stable / `D` slow) | Metadata (`B` filter/trace) | Removed or intentionally excluded (`C`) |
|---|---|---|---|
| `sku` | SKU/item identity, category/entity membership, perishability, brand/main-vendor association (`A`); sales/purchase UOM, pack factor, lead/safety configuration, designated/alternate agreement existence (`D`) | SKU/category/entity/vendor IDs, category, brand, perishability, channel, contributing source sheets/rows | inventory state/position/ROP/order units, exact agreement price/dates/count, `inventory_state` metadata, `ENGINE` snapshot lineage |
| `store` | store ID/name, entity membership, cluster, channel (`A`/`D`) | store/entity IDs, vertical, cluster, channel, source row | size/health/footfall factors, scheduled/required FTE, coverage/gap, event-derived staffing context |
| `category` | category ID/name, entity membership, perishability (`A`/`D`) | category/entity IDs, vertical, source row | current derived SKU count |
| `vendor` | vendor account/code/name/group (`A`); payment/delivery terms, currency, lead time, MOQ (`D`) | vendor account/code/group/currency, source row | OTIF, fill rate, defect rate, lead adherence, current SKU count |
| `brand` | brand identity (`A`) | brand and first supporting source row | current derived SKU count and reporting commentary |
| `vertical` | legal-entity ID/name/short name and business scope (`A`) | entity ID, vertical, short name, source row | workforce base, sales-per-FTE, peak factor and other model/KPI configuration |
| `promotion` | promotion identity/type, scope/entity/category/target, mechanism, D365 construct (`A`); value rule, threshold, supplier funding, validity (`D`) | promotion/entity/category IDs, type, validity, source row | expected uplift/current calculated performance; pre-buy output is not used |
| `brand_event` | named event, store and entity context (`A`, scoped as operational context) | store/entity IDs, event name, source row | demand-lift percentage and any invented date (the workbook has none) |
| `workbook_overview` | workbook purpose, represented verticals, shared-engine narrative (`A`) | source rows | workbook scale/counts, live/current claims, mockup/presentation instructions |
| `model_parameter` | parameter meaning/name (`A`); fixed constants and their configured values (`D`) | parameter name, source row; fixed constant value where applicable | month index and six adjustable What-If lever values are excluded from both prose and metadata |
| `formula` | metric, formula, and explanatory notes (`A`) | metric and source row | presentation/layout cells |
| `terminology` | term and definition (`A`) | term and source row | presentation/layout cells |
| `data_source` | source object, system, refresh behavior, consumer/use (`A`/`D` integration knowledge) | object/system/refresh and source row | presentation/layout cells |
| `d365_table` | mapping number, entity/table/layer/key, joins, fields, notes, confidence (`A`) | entity/table/confidence and source row | presentation/layout cells |
| `d365_field_mapping` | section plus field/table/retrieval/logic/confidence mappings (`A`) | section, structural field count, contributing source rows | presentation/layout cells; no live retrieved values are included |
| `d365_worked_example` | mapping/query/formula and explicitly illustrative example values (`A`, integration contract rather than current facts) | example SKU and contributing source rows | presentation/layout cells; examples are not asserted as live state |
| `approval_rule` | threshold, roles, and approval flow (`A`/`D`) | flow and source row | presentation/layout cells |
| `agent_spec` | agent role, trigger, output, and guardrail (`A`) | agent identity and source row | presentation/layout cells |

The hash input for every row above is only the assembled semantic-content column. `doc_key` and `source_key` remain deterministic identifiers; metadata remains deliberately narrow and JSON-filterable.

### Retrieval-domain design

The controlled vocabulary is intentionally limited to eight values:

| Domain | Intended retrieval scope | Document types | Count |
|---|---|---|---:|
| `business_entity` | durable master/entity context | `sku`, `store`, `category`, `vendor`, `brand`, `vertical` | 1,148 |
| `business_rule` | formulas, terms, and fixed/parameter meaning | `formula`, `terminology`, `model_parameter` | 44 |
| `operational_policy` | configured promotion policy/mechanism | `promotion` | 48 |
| `operational_context` | named planning context without live calculated values | `brand_event` | 23 |
| `integration` | source-system and D365 mappings/examples | `data_source`, `d365_table`, `d365_field_mapping`, `d365_worked_example` | 73 |
| `governance` | approval authority and routing | `approval_rule` | 4 |
| `agent_configuration` | agent role, output, and guardrail knowledge | `agent_spec` | 9 |
| `documentation` | corpus/workbook orientation | `workbook_overview` | 1 |

Every document gets its domain from one complete code mapping keyed by `doc_type`; callers cannot supply an arbitrary domain. Validation rejects missing, unknown, or mismatched values. `brand_event` is retained because the workbook provides a named event-to-store planning relationship useful for contextual retrieval. Its numeric demand lift is excluded, and no date is invented.

### Document and metadata contract

The frozen candidate JSONL shape is:

```json
{
  "doc_key": "...",
  "doc_type": "...",
  "retrieval_domain": "...",
  "source_sheet": "...",
  "source_key": "...",
  "content": "...",
  "metadata": {},
  "content_hash": "..."
}
```

All eight fields are required and no additional top-level field is emitted. Metadata is for low-cardinality retrieval filters, routing, relational lookup, and source traceability—not a copy of operational rows. There is no embedding/vector field and no generated timestamp. Operational values must be fetched from `retail.*` after semantic routing identifies the relevant entity/concept.

### Changes made

- Added `semantic_contract.py` as the single controlled domain vocabulary and 18-type assignment map.
- Added required top-level `retrieval_domain` to the internal model, serializer, JSONL contract, and validator.
- Removed current SKU inventory/replenishment/price statements; store staffing/model metrics; vendor service KPIs; current entity counts; promotion uplift; brand-event demand lift; vertical KPI/model values; and adjustable model-parameter values.
- Kept numeric values only when they describe a slow contract/master/business rule: pack factor, UOM relationships, lead/safety settings, vendor terms/MOQ, promotion rules/validity, fixed constants, formula definitions, and explicitly illustrative D365 examples.
- Added exact contract-field validation, controlled/deterministic-domain validation, deterministic-key validation, recursive embedding/vector-field rejection, builder-level operational leakage checks, metadata leakage checks, and JSONL count/domain reconciliation.

### Representative sample — before and after

The same 10 `doc_key` selections were preserved. All five SKU examples, the vendor, and the brand changed; the formula, terminology, and D365 mapping did not. Adding `retrieval_domain` did not change the three unchanged hashes.

| `doc_key` | Domain | Old hash | New hash | Result / removed facts and relational location |
|---|---|---|---|---|
| `sku:dgt-001` | `business_entity` | `cfea76473e7570ce4cff0771963414fb5a8e150910bd6e4b3314dce6a64750b1` | `5330518943b6e0f77de0070ba513e1599cae15662aff52558ecf90903a7bac26` | Removed state/position/ROP/order units (`InventorySnapshot`, `StoreSkuSnapshot`, `ReplenishmentProposal`) and exact price/dates (`TradeAgreement`) |
| `sku:elc-001` | `business_entity` | `382efad953f68a5172b768cd9d828f3ffeb185734f777b8523b5e738fb941395` | `a33a83a5603890414e98bb073cff7a41190455d6e86ef409e1b41ce998ac754b` | Same operational exclusions and SQL locations |
| `sku:fsh-001` | `business_entity` | `cfdbe707540ceaa3c0af52fdb7341a3bfdbd79719886889cc03ee8c4b8f259c8` | `2b0eaf26debff85c9b0ba2bd5ca299ef33ce5d86f65e8dc4c83bb709dffd22bd` | Same operational exclusions and SQL locations |
| `sku:gmr-001` | `business_entity` | `575776e6f566f57d37a8d3ae7fce305edcbd483a7ac172ab3a7f06be28f83272` | `5d3a4db62b8a3e00394873d6cd0a688ee21b6959906f8a1937dbd58e8d6fd824` | Same operational exclusions and SQL locations |
| `sku:grc-001` | `business_entity` | `7ce4bbfd7a953307821843d6cf451138d054e991beebc25c34cb871086226457` | `f70438064fd2e5740f3f4ff4df703369af174c657b2c5c81fe390a5f1f749e28` | Same operational exclusions and SQL locations |
| `vendor:v0001` | `business_entity` | `f2f78183b03171697dddf0797319644d29db586e15545316645a4f66c8a4c3d8` | `f18bcfe743d4015fd697799938222a8fc137d7c3fdabc84d71c0f1aabb8ab7ad` | Removed service KPIs and current SKU count; identity/terms remain in `Vendor`, exact product relationships in `Sku`/`TradeAgreement` |
| `brand:altura` | `business_entity` | `fc97e73ddd86cb4a8a4bb3f255f8804aeecc78e93c719806e4cd962119cc12ca` | `8bbab8a878f4f47b623349dda372f3bfd5079611a8daec2da46b411237106194` | Removed current derived SKU count; exact membership remains queryable through `Sku` |
| `formula:ads-per-store` | `business_rule` | `100571189102686a37fb1a4ba2d9ba64cbe02cf125a595ddb8d48e997cfa8f2f` | same | Semantic content unchanged |
| `terminology:ads` | `business_rule` | `b3f7ab606da082d28e73f13e32709e5068019ecd71e7db1219ddb6de683fcee4` | same | Semantic content unchanged |
| `d365-field-mapping:a1-demand-forecasting-per-vertical-aggregated-from-engine-store-forecastsales` | `integration` | `b18c8ac63e0f3facb32a81dc1bfe432a7dc90b6944031a38ba766a8b875ac357` | same | Semantic content unchanged |

Exact changed sample texts follow. These are generated values, not invented descriptions.

#### `sku:dgt-001`

**BEFORE:** SKU DGT-001 is Electronics 1 in the Electronics category of Digital & Online Retail (e-Commerce / Marketplace) (DGT). It is non-perishable, branded Brava, with main vendor Boreas Trading (V0002). It sells in EA and is bought in Carton with pack factor 24; workbook lead time is 4 days and safety coverage is 3 days. Current chain inventory state is Low: position 5684, reorder point 5813, and proposed order units 3451. Its designated trade agreement is with Boreas Trading at 610050 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreement(s) are recorded.

**AFTER:** SKU DGT-001 is Electronics 1 in the Electronics category of Digital & Online Retail (e-Commerce / Marketplace) (DGT). It is non-perishable, branded Brava, with main vendor Boreas Trading (V0002). It sells in EA and is bought in Carton with pack factor 24; workbook lead time is 4 days and safety coverage is 3 days. A designated supplier agreement is recorded with Boreas Trading (V0002). Alternate approved supplier agreements are also recorded.

#### `sku:elc-001`

**BEFORE:** SKU ELC-001 is Smartphones 1 in the Smartphones category of Consumer Electronics Retail (Electronic Super Store) (ELC). It is non-perishable, branded Brava, with main vendor Garuda Distribution (V0007). It sells in Set and is bought in Case with pack factor 3; workbook lead time is 4 days and safety coverage is 3 days. Current chain inventory state is Healthy: position 611, reorder point 582, and proposed order units 0. Its designated trade agreement is with Garuda Distribution at 7517950 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreement(s) are recorded.

**AFTER:** SKU ELC-001 is Smartphones 1 in the Smartphones category of Consumer Electronics Retail (Electronic Super Store) (ELC). It is non-perishable, branded Brava, with main vendor Garuda Distribution (V0007). It sells in Set and is bought in Case with pack factor 3; workbook lead time is 4 days and safety coverage is 3 days. A designated supplier agreement is recorded with Garuda Distribution (V0007). Alternate approved supplier agreements are also recorded.

#### `sku:fsh-001`

**BEFORE:** SKU FSH-001 is Men's Apparel 1 in the Men's Apparel category of Fashion Retail (Apparel & Footwear) (FSH). It is non-perishable, branded Brava, with main vendor Everest Wholesale (V0005). It sells in PCS and is bought in Pack with pack factor 6; workbook lead time is 7 days and safety coverage is 3 days. Current chain inventory state is Low: position 2661, reorder point 2745, and proposed order units 1181. Its designated trade agreement is with Everest Wholesale at 536800 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreement(s) are recorded.

**AFTER:** SKU FSH-001 is Men's Apparel 1 in the Men's Apparel category of Fashion Retail (Apparel & Footwear) (FSH). It is non-perishable, branded Brava, with main vendor Everest Wholesale (V0005). It sells in PCS and is bought in Pack with pack factor 6; workbook lead time is 7 days and safety coverage is 3 days. A designated supplier agreement is recorded with Everest Wholesale (V0005). Alternate approved supplier agreements are also recorded.

#### `sku:gmr-001`

**BEFORE:** SKU GMR-001 is Menswear 1 in the Menswear category of General Merchandise Retail (Department Store) (GMR). It is non-perishable, branded Nimbus, with main vendor Cendana Distribusi (V0003). It sells in Set and is bought in Box with pack factor 4; workbook lead time is 4 days and safety coverage is 3 days. Current chain inventory state is Healthy: position 727, reorder point 639, and proposed order units 0. Its designated trade agreement is with Cendana Distribusi at 203850 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreement(s) are recorded.

**AFTER:** SKU GMR-001 is Menswear 1 in the Menswear category of General Merchandise Retail (Department Store) (GMR). It is non-perishable, branded Nimbus, with main vendor Cendana Distribusi (V0003). It sells in Set and is bought in Box with pack factor 4; workbook lead time is 4 days and safety coverage is 3 days. A designated supplier agreement is recorded with Cendana Distribusi (V0003). Alternate approved supplier agreements are also recorded.

#### `sku:grc-001`

**BEFORE:** SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail (Hypermarket) (GRC). It is perishable, branded Brava, with main vendor Everest Wholesale (V0005). It sells in Bottle and is bought in Crate with pack factor 12; workbook lead time is 2 days and safety coverage is 1 day. Current chain inventory state is Low: position 1176, reorder point 1491, and proposed order units 2302. Its designated trade agreement is with Everest Wholesale at 14300 IDR per sales unit, valid from 2025-01-01 to 2026-12-31; 2 alternate agreement(s) are recorded.

**AFTER:** SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail (Hypermarket) (GRC). It is perishable, branded Brava, with main vendor Everest Wholesale (V0005). It sells in Bottle and is bought in Crate with pack factor 12; workbook lead time is 2 days and safety coverage is 1 day. A designated supplier agreement is recorded with Everest Wholesale (V0005). Alternate approved supplier agreements are also recorded.

#### `vendor:v0001`

**BEFORE:** Vendor account V0001 is Aurora Supply Co (Vendor A), classified as Import. Commercial terms are Net 30, FOB, currency USD, lead time 5 days, and MOQ 78 units. Workbook service metrics are OTIF 97.4%, fill 91.8%, defect 3.3%, and lead adherence 94.9%. It is the main vendor for 116 SKUs.

**AFTER:** Vendor account V0001 is Aurora Supply Co (Vendor A), classified as Import. Commercial terms are Net 30, FOB, currency USD, lead time 5 days, and MOQ 78 units.

#### `brand:altura`

**BEFORE:** Brand Altura appears in the SKU master and is assigned to 67 SKUs in the workbook. Brand-level performance measures are derived reporting outputs and exact SKU or inventory figures should be queried from SQL.

**AFTER:** Brand Altura is a product-brand identity recorded in the SKU master.

The three unchanged texts are exactly identical before/after: `formula:ads-per-store`, `terminology:ads`, and the selected D365 field mapping. Their unchanged hashes prove that top-level routing/metadata contract changes do not force re-embedding when semantic content is unchanged.

### Validation results

- Corpus cardinality: **1,350 before / 1,350 after**; every one of the same 18 document types and deterministic keys is retained.
- Type counts: `sku` 800, `store` 160, `category` 160, `promotion` 48, `d365_table` 33, `d365_field_mapping` 29, `brand_event` 23, `formula` 19, `terminology` 13, `brand` 12, `model_parameter` 12, `data_source` 10, `agent_spec` 9, `vendor` 8, `vertical` 8, `approval_rule` 4, `d365_worked_example` 1, `workbook_overview` 1.
- Domain counts: `business_entity` 1,148; `business_rule` 44; `operational_policy` 48; `operational_context` 23; `integration` 73; `governance` 4; `agent_configuration` 9; `documentation` 1.
- Sample validation: 10/10 objects valid and the same 10 keys retained. Full validation: 1,350/1,350 object lines valid; 1,350 unique deterministic keys; hashes valid and matched; metadata serializable; traceability present; no credential content; no embedding/vector fields; no unintentionally duplicated semantic content.
- Byte-level deterministic regeneration passed: full JSONL SHA-256 remained `f2a04b34a725f1e06a6c547fb7ab4ae1dd294a1365ca0a76c3cf2191008aa567`; sample JSONL remained `194368f80b942933f072b2151500951e03e82d156f27d303d9b695fbb55b22f0`.
- Explicit leakage guardrails cover current SKU inventory/replenishment text, store workforce snapshot text, vendor service KPIs, derived brand/category counts, promotion expected uplift, brand-event demand lift, vertical KPI values, and adjustable model-parameter values/metadata.
- Content length is 37–4,139 characters (average 368.53). The only warning is the intentional short but complete `terminology:dos` definition.
- Independent source-normalization validation remains valid at 21,571 rows, zero duplicate primary keys, and zero FK violations. No live SQL validation or database mutation was needed for this semantic-only phase.

### Content-hash contract and tests

`content_hash = SHA256(canonicalize(content).encode("utf-8"))`. Canonicalization normalizes content whitespace only. It excludes metadata, `retrieval_domain`, trace fields, load/source IDs, timestamps, and all removed operational snapshots. Regression tests prove:

- identical semantic text with different metadata produces the same hash;
- changed semantic text produces a different hash;
- adding the top-level domain leaves an unchanged document's hash unchanged;
- repeated full generation produces byte-identical JSONL and stable hashes;
- every generated and JSONL hash recalculates correctly from `content`.

### Test results

- Focused bootstrap suite: **23 passed, 1 skipped** (the skipped test is explicitly opt-in live Azure integration).
- Maintained backend suite: **274 passed, 1 skipped** in 15.25 seconds.
- Package/test compilation: passed.
- The pre-existing repository-root collection caveat remains: `backend/test_retail_tool.py` performs a D365 call at import and is not part of `backend/tests/`; Phase 4.5 did not alter it.

### Unresolved questions

- Business owners should confirm that promotion validity, rule values, vendor terms/MOQ, SKU lead/safety settings, and pack/UOM relationships are sufficiently slow-changing to justify re-embedding when they change. This implementation treats them as contractual/master meaning, not live measurements.
- Business owners should confirm that named `Brand Events` are worth retrieving as `operational_context` despite the source providing no dates. The implementation retains event identity and routing context, removes demand lift, and invents no date.
- Confirm whether adjustable model-parameter documents should remain as semantic descriptions without current values. The current contract keeps their meaning discoverable while requiring SQL/runtime configuration for the active value.
- The short `terminology:dos` document is accurate but may have weak standalone retrieval signal; it is retained because it is a genuine glossary entry.

### Freeze recommendation

**Recommend freezing this semantic contract after human review of the three policy questions above.** Technically, the contract is complete and deterministic: every type is audited, every document has one controlled domain, volatile operational facts are separated from embedding text, sample/full corpora validate, counts reconcile, and all maintained tests pass. The `retail.*` relational schema/data was not modified, reloaded, or queried live, and no embedding, vector table, vector index, API integration, or frontend work was performed.

The exact next Phase 5 step—only after approval—is to define a separate versioned `ai` document/vector storage migration and embedding pipeline contract that consumes these eight JSONL fields, selects an embedding model/dimension, embeds only new or changed `content_hash` values, reuses unchanged embeddings, upserts atomically, and validates dimensions/counts. Phase 5 must not start until this Phase 4.5 freeze is approved.
