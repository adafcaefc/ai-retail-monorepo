WITH latest_batch AS (
    SELECT id
    FROM audit.import_batches
    WHERE agent_name = 'collections_credit_agent'
      AND import_status = 'COMPLETED'
    ORDER BY imported_at DESC
    LIMIT 1
)
SELECT
    'assumptions' AS table_name,
    COUNT(*) AS row_count
FROM collections.assumptions
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'customer_credit_aging',
    COUNT(*)
FROM collections.customer_credit_aging
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'risk_scores',
    COUNT(*)
FROM collections.risk_scores
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'dso_cash_impact',
    COUNT(*)
FROM collections.dso_cash_impact
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'risk_tier_exposure',
    COUNT(*)
FROM collections.risk_tier_exposure
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'worklist',
    COUNT(*)
FROM collections.worklist
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

UNION ALL

SELECT
    'recommendations',
    COUNT(*)
FROM collections.recommendations
WHERE import_batch_id = (
    SELECT id FROM latest_batch
)

ORDER BY table_name;