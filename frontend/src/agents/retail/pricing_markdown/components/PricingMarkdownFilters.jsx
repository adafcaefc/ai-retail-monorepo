import { ALL, LADDER_HORIZONS, STATE_ORDER } from "../data/contract.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

/**
 * The top filter row: vertical, category, store, inventory state, and a
 * free-text search across SKU, name, vendor and brand.
 *
 * `store_id` narrows `by_store`/`by_cluster`/`by_channel`
 * (selectors.js's scopeStores) AND, when the board is reading from the API
 * (see dataSource.js), narrows `items` itself: dashboard.py's `build()`
 * recomputes each item's state/at-risk/recoverable at that one store's
 * grain rather than its chain-wide total, and a SKU the store does not stock
 * drops out entirely. Running off the bundled fixture (standalone/offline
 * builds only) still shows the chain-wide `items` regardless of store,
 * since that path has no backend to rerun the aggregation against.
 *
 * `category_group` and `state` also narrow `by_store`/`by_cluster`/
 * `by_channel`/`by_legal_entity` (DimensionCharts), but only when the board
 * is reading from the API: dashboard.py's `build()` re-aggregates the store
 * rollup from category/state-filtered rows before scopeStores ever sees it,
 * since a store row has already summed away category/state by the time it
 * exists (unlike store_id, which is still an intrinsic field on that row and
 * so stays filterable client-side). The bundled fixture has no equivalent
 * recompute step, so those four charts keep showing each store's full
 * all-category/all-state total there, regardless of category/state filter.
 */
export default function PricingMarkdownFilters({
  scope,
  options,
  busy,
  onPatch,
  onSearch,
  onRefresh,
  onClear,
  ladderHorizon,
  onLadderHorizonChange,
}) {
  const { t } = useLanguage();
  const hasFilter =
    scope.legal_entity_id !== ALL ||
    scope.category_group !== ALL ||
    scope.store_id !== ALL ||
    scope.state !== ALL ||
    (scope.sku && scope.sku.trim());

  return (
    <div className="pricing-filters" data-testid="pricing-filters">
      <SelectField
        label={t("Vertical")}
        value={scope.legal_entity_id}
        options={options.legal_entities}
        disabled={busy}
        onChange={(value) =>
          // A category or store from the previous vertical cannot exist
          // under the new one, so reset both rather than load a stale scope.
          onPatch({ legal_entity_id: value, category_group: ALL, store_id: ALL })
        }
      />
      <SelectField
        label={t("Category")}
        value={scope.category_group}
        options={categoriesInScope(options.categories, scope.legal_entity_id)}
        disabled={busy}
        onChange={(value) => onPatch({ category_group: value })}
      />
      <SelectField
        label={t("Store")}
        value={scope.store_id}
        options={storesInScope(options.stores, scope.legal_entity_id)}
        disabled={busy}
        onChange={(value) => onPatch({ store_id: value })}
      />
      <SelectField
        label={t("State")}
        value={scope.state}
        options={STATE_ORDER.map((state) => ({ value: state, label: t(state) }))}
        disabled={busy}
        onChange={(value) => onPatch({ state: value })}
      />
      {onLadderHorizonChange ? (
        <fieldset className="pricing-horizon">
          <legend>{t("Horizon")}</legend>
          <div className="pricing-segmented">
            {LADDER_HORIZONS.map((weeks) => (
              <button
                key={weeks}
                type="button"
                aria-pressed={ladderHorizon === weeks}
                onClick={() => onLadderHorizonChange(weeks)}
              >
                {weeks}w
              </button>
            ))}
          </div>
        </fieldset>
      ) : null}
      <label className="pricing-search">
        <span className="pricing-search-label">{t("Search")}</span>
        <input
          type="search"
          value={scope.sku}
          placeholder={t("SKU, name, vendor, brand")}
          onChange={(event) => onSearch(event.target.value)}
        />
      </label>
      <button type="button" className="pricing-button" onClick={onRefresh} disabled={busy}>
        {t("Refresh")}
      </button>
      {hasFilter ? (
        <button type="button" className="pricing-button" onClick={onClear}>
          {t("Clear all")}
        </button>
      ) : null}
    </div>
  );
}

function categoriesInScope(categories, vertical) {
  if (!vertical || vertical === ALL) return categories;
  return categories.filter((c) => c.legal_entity_id === vertical);
}

function storesInScope(stores, vertical) {
  if (!vertical || vertical === ALL) return stores;
  return stores.filter((s) => s.legal_entity_id === vertical);
}

function SelectField({ label, value, options, disabled, onChange }) {
  const { t } = useLanguage();
  return (
    <label className="pricing-select">
      <span className="pricing-select-label">{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value={ALL}>{t("All")}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
