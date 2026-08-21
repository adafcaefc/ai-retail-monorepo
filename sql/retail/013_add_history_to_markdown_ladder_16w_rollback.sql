-- Rollback of 013: drop the history columns, leaving the forward-only
-- table (migration 012) exactly as it was before this migration.
--
-- Data-only demo columns: nothing in `retail` references them, so dropping
-- them loses no workbook fact. The chart falls back to its forward-only
-- shape (a missing history column is read the same way a missing table is
-- guarded elsewhere on this board -- a soft failure by design, see
-- dashboard.py's `_ladder_by_vertical()`).

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'synthetic.markdown_ladder_store_sku_16w', N'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_synthetic_markdown_ladder_store_sku_16w_hist_non_negative'
    )
        ALTER TABLE synthetic.markdown_ladder_store_sku_16w
            DROP CONSTRAINT CK_synthetic_markdown_ladder_store_sku_16w_hist_non_negative;

    IF COL_LENGTH(N'synthetic.markdown_ladder_store_sku_16w', N'no_action_hist_w1') IS NOT NULL
        ALTER TABLE synthetic.markdown_ladder_store_sku_16w DROP COLUMN
            no_action_hist_w1, no_action_hist_w2, no_action_hist_w3, no_action_hist_w4,
            no_action_hist_w5, no_action_hist_w6, no_action_hist_w7, no_action_hist_w8,
            no_action_hist_w9, no_action_hist_w10, no_action_hist_w11, no_action_hist_w12,
            no_action_hist_w13, no_action_hist_w14, no_action_hist_w15, no_action_hist_w16,
            ladder_hist_w1, ladder_hist_w2, ladder_hist_w3, ladder_hist_w4,
            ladder_hist_w5, ladder_hist_w6, ladder_hist_w7, ladder_hist_w8,
            ladder_hist_w9, ladder_hist_w10, ladder_hist_w11, ladder_hist_w12,
            ladder_hist_w13, ladder_hist_w14, ladder_hist_w15, ladder_hist_w16;
END
GO
