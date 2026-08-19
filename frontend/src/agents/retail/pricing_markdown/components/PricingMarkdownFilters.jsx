import { ALL, STATE_ORDER } from "../data/contract.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

/**
 * The top filter row: vertical, category, inventory state, and a free-text
 * search across SKU, name, vendor and brand.
 *
 * No store filter: `store_id` would only ever narrow
 * `by_store`/`by_cluster`/`by_channel` (selectors.js's scopeStores), never
 * `items` -- a SKU's own at-risk/recoverable value is a chain-wide figure
 * across all its stores, not a per-store one (see dashboard.py's module
 * docstring for the backend side of that same rule) -- so a store control
 * here would filter the dimension charts while leaving every KPI card and
 * the candidate table unchanged, which reads as broken rather than scoped.
 */
export default function PricingMarkdownFilters({
  scope,
  options,
  busy,
  onPatch,
  onSearch,
  onRefresh,
  onClear,
}) {
  const { t } = useLanguage();
  const hasFilter =
    scope.legal_entity_id !== ALL ||
    scope.category_group !== ALL ||
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
          // A category from the previous vertical cannot exist under the
          // new one, so reset it rather than load a stale scope.
          onPatch({ legal_entity_id: value, category_group: ALL })
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
        label={t("State")}
        value={scope.state}
        options={STATE_ORDER.map((state) => ({ value: state, label: t(state) }))}
        disabled={busy}
        onChange={(value) => onPatch({ state: value })}
      />
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
