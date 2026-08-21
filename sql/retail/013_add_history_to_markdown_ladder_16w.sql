-- 013: add a 16-week modelled HISTORY side to the markdown ladder projection.
--
-- `synthetic.markdown_ladder_store_sku_16w` (migration 012) shipped
-- forward-only: `no_action_w1` ("today", the real calibration anchor) through
-- `no_action_w16` (+15 weeks). This migration adds the mirror image going
-- back: `no_action_hist_w1` (1 week before today) through `no_action_hist_w16`
-- (16 weeks before), and the matching `ladder_hist_w*` columns -- so the A5
-- chart can draw a continuous W-16..today..W+15 line instead of a
-- forward-only one.
--
-- At-risk value still has no real past to record (unchanged fact from
-- migration 012's own docstring) -- the history side is modelled the same
-- way the forward side already was, not a second, different kind of
-- assumption. See scripts/generate_synthetic_markdown_ladder_16w.py's module
-- docstring for the exact formula and the gates it passed before being
-- written.
--
-- A new migration rather than editing 012: this table has already been
-- seeded once (16,000 rows), and 012 is not touched or renumbered. The
-- DEFAULT 0 on the new columns only matters for the instant between this
-- ALTER and the full delete+insert reseed that follows
-- (scripts/seed_synthetic_markdown_ladder_16w.py replaces every row, so the
-- default never actually ships to a reader).
--
-- Purely additive: does not touch, alter, or rename any existing column on
-- this table, and does not touch `synthetic.demand_store_sku_32w`,
-- `synthetic.inbound_store_sku_16w`, or any `retail.*` table.
--
-- Rollback: 013_add_history_to_markdown_ladder_16w_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'synthetic.markdown_ladder_store_sku_16w', N'U') IS NULL
    THROW 50013, 'synthetic.markdown_ladder_store_sku_16w does not exist; run migration 012 first.', 1;
GO

IF COL_LENGTH(N'synthetic.markdown_ladder_store_sku_16w', N'no_action_hist_w1') IS NOT NULL
    THROW 50013, 'synthetic.markdown_ladder_store_sku_16w already has history columns; this migration only adds them.', 1;
GO

ALTER TABLE synthetic.markdown_ladder_store_sku_16w ADD
    no_action_hist_w1  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h1  DEFAULT 0,
    no_action_hist_w2  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h2  DEFAULT 0,
    no_action_hist_w3  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h3  DEFAULT 0,
    no_action_hist_w4  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h4  DEFAULT 0,
    no_action_hist_w5  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h5  DEFAULT 0,
    no_action_hist_w6  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h6  DEFAULT 0,
    no_action_hist_w7  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h7  DEFAULT 0,
    no_action_hist_w8  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h8  DEFAULT 0,
    no_action_hist_w9  DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h9  DEFAULT 0,
    no_action_hist_w10 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h10 DEFAULT 0,
    no_action_hist_w11 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h11 DEFAULT 0,
    no_action_hist_w12 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h12 DEFAULT 0,
    no_action_hist_w13 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h13 DEFAULT 0,
    no_action_hist_w14 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h14 DEFAULT 0,
    no_action_hist_w15 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h15 DEFAULT 0,
    no_action_hist_w16 DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_na_h16 DEFAULT 0,
    ladder_hist_w1      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h1  DEFAULT 0,
    ladder_hist_w2      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h2  DEFAULT 0,
    ladder_hist_w3      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h3  DEFAULT 0,
    ladder_hist_w4      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h4  DEFAULT 0,
    ladder_hist_w5      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h5  DEFAULT 0,
    ladder_hist_w6      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h6  DEFAULT 0,
    ladder_hist_w7      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h7  DEFAULT 0,
    ladder_hist_w8      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h8  DEFAULT 0,
    ladder_hist_w9      DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h9  DEFAULT 0,
    ladder_hist_w10     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h10 DEFAULT 0,
    ladder_hist_w11     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h11 DEFAULT 0,
    ladder_hist_w12     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h12 DEFAULT 0,
    ladder_hist_w13     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h13 DEFAULT 0,
    ladder_hist_w14     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h14 DEFAULT 0,
    ladder_hist_w15     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h15 DEFAULT 0,
    ladder_hist_w16     DECIMAL(20,6) NOT NULL CONSTRAINT DF_mdl16w_ld_h16 DEFAULT 0;
GO

ALTER TABLE synthetic.markdown_ladder_store_sku_16w ADD CONSTRAINT
    CK_synthetic_markdown_ladder_store_sku_16w_hist_non_negative CHECK (
        no_action_hist_w1 >= 0 AND no_action_hist_w2 >= 0 AND no_action_hist_w3 >= 0 AND no_action_hist_w4 >= 0 AND
        no_action_hist_w5 >= 0 AND no_action_hist_w6 >= 0 AND no_action_hist_w7 >= 0 AND no_action_hist_w8 >= 0 AND
        no_action_hist_w9 >= 0 AND no_action_hist_w10 >= 0 AND no_action_hist_w11 >= 0 AND no_action_hist_w12 >= 0 AND
        no_action_hist_w13 >= 0 AND no_action_hist_w14 >= 0 AND no_action_hist_w15 >= 0 AND no_action_hist_w16 >= 0 AND
        ladder_hist_w1 >= 0 AND ladder_hist_w2 >= 0 AND ladder_hist_w3 >= 0 AND ladder_hist_w4 >= 0 AND
        ladder_hist_w5 >= 0 AND ladder_hist_w6 >= 0 AND ladder_hist_w7 >= 0 AND ladder_hist_w8 >= 0 AND
        ladder_hist_w9 >= 0 AND ladder_hist_w10 >= 0 AND ladder_hist_w11 >= 0 AND ladder_hist_w12 >= 0 AND
        ladder_hist_w13 >= 0 AND ladder_hist_w14 >= 0 AND ladder_hist_w15 >= 0 AND ladder_hist_w16 >= 0
    );
GO
