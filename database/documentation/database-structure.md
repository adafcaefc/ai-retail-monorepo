# Database Structure

This document describes the PostgreSQL schema defined by the migrations in `database/migrations/`.

## Connection

The application reads the database connection from the `DATABASE_URL` environment variable. Do not commit the value of that variable or any database credentials to this repository.

## Migration Order

1. `001_create_cashflow_foundation.sql` creates the shared audit table and schemas.
2. `002_create_cashflow_tables.sql` creates the Treasury/cashflow tables.
3. `003_create_collections_tables.sql` creates the Collections tables.

## Schemas

| Schema | Purpose |
|---|---|
| `audit` | Import lineage, status, and source workbook metadata |
| `cashflow` | Treasury, liquidity, payables, collections timing, FX, and recommendations |
| `collections` | Customer credit, aging, risk, DSO, recovery worklists, and recommendations |
| `app` | Reserved application schema; no tables are currently created by the migrations |

## Relationship Overview

All domain tables use `import_batch_id` to reference `audit.import_batches(id)` with `ON DELETE CASCADE`.

```mermaid
erDiagram
    audit_import_batches ||--o{ cashflow_assumptions : contains
    audit_import_batches ||--o{ cashflow_ar_collections : contains
    audit_import_batches ||--o{ cashflow_ap_payables : contains
    audit_import_batches ||--o{ cashflow_other_outflows : contains
    audit_import_batches ||--o{ cashflow_weekly_forecast : contains
    audit_import_batches ||--o{ cashflow_fx_scenarios : contains
    audit_import_batches ||--o{ cashflow_recommendations : contains
    audit_import_batches ||--o{ collections_assumptions : contains
    audit_import_batches ||--o{ customer_credit_aging : contains
    audit_import_batches ||--o{ risk_scores : contains
    audit_import_batches ||--o{ dso_cash_impact : contains
    audit_import_batches ||--o{ risk_tier_exposure : contains
    audit_import_batches ||--o{ collections_worklist : contains
    audit_import_batches ||--o{ collections_recommendations : contains
```

## Shared Audit Schema

### `audit.import_batches`

One row represents one attempted workbook import. Domain records are scoped to this batch.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `agent_name` | `VARCHAR(100)` | No | Indexed |
| `workbook_name` | `VARCHAR(255)` | No | |
| `workbook_version` | `VARCHAR(100)` | Yes | |
| `workbook_path` | `VARCHAR(500)` | Yes | |
| `import_status` | `VARCHAR(30)` | No | `STARTED`; allowed: `STARTED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `imported_by` | `VARCHAR(255)` | Yes | |
| `imported_at` | `TIMESTAMPTZ` | No | `CURRENT_TIMESTAMP`; indexed descending |
| `completed_at` | `TIMESTAMPTZ` | Yes | |
| `total_sheets` | `INTEGER` | No | `0` |
| `total_rows` | `INTEGER` | No | `0` |
| `error_message` | `TEXT` | Yes | |
| `metadata` | `JSONB` | No | `'{}'` |

Indexes: `agent_name`, `imported_at DESC`, and `import_status`.

## Cashflow Schema

All cashflow tables have a `BIGSERIAL` primary key named `id`, a required `import_batch_id` foreign key, a `source_sheet` column, and a `created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP` column unless noted otherwise below.

### `cashflow.assumptions`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `assumption_group` | `VARCHAR(100)` | No | |
| `assumption_name` | `VARCHAR(255)` | No | |
| `numeric_value` | `NUMERIC(20,6)` | Yes | |
| `text_value` | `TEXT` | Yes | |
| `date_value` | `DATE` | Yes | |
| `unit` | `VARCHAR(50)` | Yes | |
| `notes` | `TEXT` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `02 Assumptions` |

Unique key: (`import_batch_id`, `assumption_group`, `assumption_name`).

### `cashflow.ar_collections`

AR collection timing and invoice-level balances. Amount columns ending in `_idr_mn` are IDR millions.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `invoice_number` | `VARCHAR(50)` | No | |
| `customer_name` | `VARCHAR(255)` | No | |
| `customer_segment` | `VARCHAR(100)` | Yes | |
| `invoice_date` | `DATE` | Yes | |
| `payment_terms_days` | `INTEGER` | Yes | |
| `due_date` | `DATE` | Yes | |
| `original_week` | `INTEGER` | Yes | `1`-`13` when present |
| `expected_week` | `INTEGER` | Yes | `1`-`13` when present; indexed |
| `currency` | `VARCHAR(10)` | No | |
| `amount_idr_mn` | `NUMERIC(20,2)` | Yes | |
| `usd_amount` | `NUMERIC(20,2)` | Yes | |
| `idr_value_mn` | `NUMERIC(20,2)` | Yes | |
| `delay_flag` | `VARCHAR(100)` | Yes | |
| `notes` | `TEXT` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `03 AR Collections` |

Unique key: (`import_batch_id`, `invoice_number`).

### `cashflow.ap_payables`

Accounts payable and payment timing. Amount columns ending in `_idr_mn` are IDR millions.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `bill_number` | `VARCHAR(50)` | No | |
| `vendor_name` | `VARCHAR(255)` | No | |
| `category` | `VARCHAR(255)` | Yes | |
| `payment_terms_days` | `INTEGER` | Yes | |
| `due_date` | `DATE` | Yes | |
| `payment_week` | `INTEGER` | Yes | `1`-`13` when present; indexed |
| `currency` | `VARCHAR(10)` | No | |
| `amount_idr_mn` | `NUMERIC(20,2)` | Yes | |
| `usd_amount` | `NUMERIC(20,2)` | Yes | |
| `idr_value_mn` | `NUMERIC(20,2)` | Yes | |
| `is_deferrable` | `BOOLEAN` | No | `FALSE` |
| `notes` | `TEXT` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `04 AP USD Payables` |

Unique key: (`import_batch_id`, `bill_number`).

### `cashflow.other_outflows`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `category` | `VARCHAR(255)` | No | |
| `week_number` | `INTEGER` | No | `1`-`13` |
| `amount_idr_mn` | `NUMERIC(20,2)` | No | `0`; IDR millions |
| `source_sheet` | `VARCHAR(100)` | No | `05 Other Outflows` |

Unique key: (`import_batch_id`, `category`, `week_number`).

### `cashflow.weekly_forecast`

Thirteen-week cash forecast. Monetary columns are IDR millions.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `week_number` | `INTEGER` | No | `1`-`13` |
| `week_start` | `DATE` | Yes | |
| `week_end` | `DATE` | Yes | |
| `customer_collections_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `total_inflows_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `vendor_payments_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `vendor_payments_usd_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `payroll_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `rent_utilities_opex_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `taxes_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `loan_repayment_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `total_outflows_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `net_cash_flow_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `opening_cash_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `closing_cash_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `minimum_buffer_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `headroom_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `status` | `VARCHAR(30)` | No | Allowed: `OK`, `SHORTAGE`, `RISK` |
| `source_sheet` | `VARCHAR(100)` | No | `06 Cash Forecast 13W` |

Unique key: (`import_batch_id`, `week_number`).

### `cashflow.fx_scenarios`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `scenario_name` | `VARCHAR(255)` | No | |
| `action_description` | `TEXT` | Yes | |
| `usd_exposure` | `NUMERIC(20,2)` | Yes | |
| `fx_rate_idr_per_usd` | `NUMERIC(20,4)` | Yes | |
| `movement_vs_spot` | `NUMERIC(20,4)` | Yes | |
| `fx_cash_impact_idr_mn` | `NUMERIC(20,2)` | Yes | IDR millions |
| `downside_avoided_idr_mn` | `NUMERIC(20,2)` | Yes | IDR millions |
| `premium_idr_mn` | `NUMERIC(20,2)` | Yes | IDR millions |
| `liquidity_effect` | `TEXT` | Yes | |
| `confidence_label` | `VARCHAR(100)` | Yes | |
| `notes` | `TEXT` | Yes | |
| `is_recommended` | `BOOLEAN` | No | `FALSE` |
| `source_sheet` | `VARCHAR(100)` | No | `07 FX Scenarios` |

Unique key: (`import_batch_id`, `scenario_name`).

### `cashflow.recommendations`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `recommendation_type` | `VARCHAR(50)` | No | `LIQUIDITY`, `FX`, or `GOVERNANCE` |
| `recommendation_order` | `INTEGER` | No | `1` |
| `action_title` | `VARCHAR(255)` | No | |
| `action_description` | `TEXT` | No | |
| `expected_impact` | `TEXT` | Yes | |
| `assumptions` | `JSONB` | No | `'[]'` |
| `risks` | `JSONB` | No | `'[]'` |
| `requires_approval` | `BOOLEAN` | No | `TRUE` |
| `approval_route` | `VARCHAR(255)` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `08 Recommendation` |

## Collections Schema

All collections tables have a `BIGSERIAL` primary key named `id`, a required `import_batch_id` foreign key, a `source_sheet` column, and a `created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP` column unless noted otherwise below.

### `collections.assumptions`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `assumption_group` | `VARCHAR(100)` | No | |
| `assumption_name` | `VARCHAR(255)` | No | |
| `numeric_value` | `NUMERIC(24,8)` | Yes | |
| `text_value` | `TEXT` | Yes | |
| `unit` | `VARCHAR(50)` | Yes | |
| `notes` | `TEXT` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `01 Assumptions` |

Unique key: (`import_batch_id`, `assumption_group`, `assumption_name`).

### `collections.customer_credit_aging`

Customer-level credit exposure and aging buckets. Amount columns ending in `_idr_mn` are IDR millions; percentage values are stored as numeric fractions or percentages according to the imported workbook convention.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `customer_id` | `VARCHAR(50)` | No | |
| `customer_name` | `VARCHAR(255)` | No | |
| `customer_segment` | `VARCHAR(100)` | Yes | |
| `payment_terms` | `VARCHAR(50)` | Yes | |
| `currency` | `VARCHAR(10)` | No | `IDR` or `USD` |
| `credit_limit_idr_mn` | `NUMERIC(20,2)` | Yes | Non-negative when present |
| `days_beyond_terms` | `INTEGER` | No | `0` or greater |
| `payment_trend` | `VARCHAR(30)` | Yes | `Improving`, `Stable`, or `Worsening` |
| `has_dispute` | `BOOLEAN` | No | `FALSE` |
| `on_time_percentage` | `NUMERIC(12,8)` | Yes | |
| `current_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_1_30_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_31_60_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_61_90_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_90_plus_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `total_ar_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_idr_mn` | `NUMERIC(20,2)` | No | `0`; non-negative |
| `overdue_percentage` | `NUMERIC(12,8)` | Yes | |
| `credit_utilization` | `NUMERIC(12,8)` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `02 Customer Credit & Aging` |

Unique key: (`import_batch_id`, `customer_id`).

### `collections.risk_scores`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `customer_id` | `VARCHAR(50)` | No | |
| `customer_name` | `VARCHAR(255)` | No | |
| `balance_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `utilization_percentage` | `NUMERIC(12,8)` | Yes | |
| `overdue_61_plus_idr_mn` | `NUMERIC(20,2)` | No | `0` |
| `overdue_severity_percentage` | `NUMERIC(12,8)` | Yes | |
| `days_beyond_terms` | `INTEGER` | No | `0` |
| `payment_trend` | `VARCHAR(30)` | Yes | |
| `has_dispute` | `BOOLEAN` | No | `FALSE` |
| `dbt_points` | `NUMERIC(12,6)` | No | `0` |
| `severity_points` | `NUMERIC(12,6)` | No | `0` |
| `utilization_points` | `NUMERIC(12,6)` | No | `0` |
| `trend_points` | `NUMERIC(12,6)` | No | `0` |
| `dispute_points` | `NUMERIC(12,6)` | No | `0` |
| `risk_score` | `NUMERIC(12,6)` | No | `0`-`100` |
| `risk_tier` | `VARCHAR(20)` | No | `Low`, `Medium`, or `High` |
| `risk_rank` | `INTEGER` | No | Greater than `0` |
| `source_sheet` | `VARCHAR(100)` | No | `03 Risk Scoring` |

Unique key: (`import_batch_id`, `customer_id`).

### `collections.dso_cash_impact`

One aggregate DSO and cash-impact row per import batch. Amount columns ending in `_idr_mn` are IDR millions.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK; unique per batch |
| `total_ar_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `current_ar_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `overdue_ar_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `overdue_percentage` | `NUMERIC(12,8)` | No | |
| `annual_credit_sales_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `daily_credit_sales_idr_mn` | `NUMERIC(20,8)` | No | Non-negative |
| `current_dso_days` | `NUMERIC(12,6)` | No | Non-negative |
| `target_dso_days` | `NUMERIC(12,6)` | No | Non-negative |
| `dso_gap_days` | `NUMERIC(12,6)` | No | |
| `cash_freed_at_target_idr_mn` | `NUMERIC(20,8)` | No | Non-negative |
| `high_risk_provision_idr_mn` | `NUMERIC(20,2)` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `04 DSO & Cash Impact` |

### `collections.risk_tier_exposure`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `risk_tier` | `VARCHAR(20)` | No | `Low`, `Medium`, or `High` |
| `customer_count` | `INTEGER` | No | Non-negative |
| `exposure_idr_mn` | `NUMERIC(20,2)` | No | Non-negative; IDR millions |
| `percentage_of_ar` | `NUMERIC(12,8)` | No | Non-negative |
| `notes` | `TEXT` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `04 DSO & Cash Impact` |

Unique key: (`import_batch_id`, `risk_tier`).

### `collections.worklist`

Prioritized recovery actions. Amount columns ending in `_idr_mn` are IDR millions.

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `priority_rank` | `INTEGER` | No | Greater than `0` |
| `customer_name` | `VARCHAR(255)` | No | |
| `customer_segment` | `VARCHAR(100)` | Yes | |
| `overdue_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `oldest_aging_bucket` | `VARCHAR(50)` | Yes | |
| `risk_tier` | `VARCHAR(20)` | No | `Low`, `Medium`, or `High` |
| `risk_score` | `NUMERIC(12,6)` | No | `0`-`100` |
| `recommended_action` | `TEXT` | No | |
| `recovery_percentage` | `NUMERIC(12,8)` | No | `0`-`1` |
| `expected_recovery_idr_mn` | `NUMERIC(20,2)` | No | Non-negative |
| `source_sheet` | `VARCHAR(100)` | No | `05 Collections Worklist` |

Unique key: (`import_batch_id`, `priority_rank`).

### `collections.recommendations`

| Column | Type | Null | Default / constraints |
|---|---|---:|---|
| `id` | `BIGSERIAL` | No | Primary key |
| `import_batch_id` | `BIGINT` | No | FK to `audit.import_batches` |
| `recommendation_type` | `VARCHAR(30)` | No | `ACCELERATE`, `CONTAIN`, or `PREVENT` |
| `recommendation_order` | `INTEGER` | No | Greater than `0` |
| `action_title` | `VARCHAR(255)` | No | |
| `action_description` | `TEXT` | No | |
| `expected_impact` | `TEXT` | Yes | |
| `requires_approval` | `BOOLEAN` | No | `TRUE` |
| `approval_route` | `VARCHAR(255)` | Yes | |
| `source_sheet` | `VARCHAR(100)` | No | `06 Recommendation` |

Unique key: (`import_batch_id`, `recommendation_order`).

## Index Summary

| Table | Index coverage |
|---|---|
| `audit.import_batches` | `agent_name`, `imported_at DESC`, `import_status` |
| `cashflow.assumptions` | `import_batch_id` |
| `cashflow.ar_collections` | `import_batch_id`, `expected_week` |
| `cashflow.ap_payables` | `import_batch_id`, `payment_week` |
| `cashflow.other_outflows` | `import_batch_id` |
| `cashflow.weekly_forecast` | `import_batch_id` |
| `cashflow.fx_scenarios` | `import_batch_id` |
| `cashflow.recommendations` | `import_batch_id` |
| `collections.assumptions` | `import_batch_id` |
| `collections.customer_credit_aging` | `import_batch_id`, `overdue_idr_mn DESC` within batch |
| `collections.risk_scores` | `import_batch_id`, `risk_tier` within batch, `risk_rank` within batch |
| `collections.dso_cash_impact` | `import_batch_id` |
| `collections.risk_tier_exposure` | `import_batch_id` |
| `collections.worklist` | `import_batch_id`, `priority_rank` within batch |
| `collections.recommendations` | `import_batch_id` |

## Data Loading Rules

- Import records should be written under a new `audit.import_batches` row.
- Domain queries should select a completed batch before reading its related records.
- Deleting an import batch deletes all related domain records through cascading foreign keys.
- `source_sheet` preserves the workbook sheet that produced each record.
- Monetary fields named with `_idr_mn` represent IDR millions; fields named `usd_amount` or `usd_exposure` represent USD values.
- Week fields constrained to `1` through `13` represent the thirteen-week cashflow horizon.

## Source of Truth

The SQL migrations are authoritative. Update this document when a migration changes, and keep credentials only in local environment configuration.
