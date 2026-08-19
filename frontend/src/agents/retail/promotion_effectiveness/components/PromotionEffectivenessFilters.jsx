import { ALL } from "../data/contract.js";
import { SUPPORTS_STORE_SCOPE } from "../data/selectors.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

/**
 * The top filter row: vertical, category, store, and a free-text search
 * across SKU, promo name and category. Mirrors the sibling boards' filter
 * contract.
 */
export default function PromotionEffectivenessFilters({
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
    scope.store_id !== ALL ||
    scope.horizon_weeks !== 16 ||
    (scope.sku && scope.sku.trim());

  return (
    <div className="promo-filters" data-testid="promo-filters">
      <SelectField
        label={t("Vertical")}
        value={scope.legal_entity_id}
        options={options.legal_entities}
        disabled={busy}
        onChange={(value) =>
          // A category or store from the previous vertical cannot exist under
          // the new one, so reset both rather than load a stale scope.
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
        disabled={busy || !SUPPORTS_STORE_SCOPE}
        title={
          SUPPORTS_STORE_SCOPE
            ? t("Shows this store's own position, not the chain's share of it.")
            : t("Store scope needs the per-store dataset, not yet available.")
        }
        onChange={(value) => onPatch({ store_id: value })}
      />
      <fieldset className="promo-horizon">
        <legend>{t("Horizon")}</legend>
        <div className="promo-segmented">
          {(options.horizons_weeks ?? []).map((weeks) => (
            <button
              key={weeks}
              type="button"
              aria-pressed={scope.horizon_weeks === weeks}
              disabled={busy}
              onClick={() => onPatch({ horizon_weeks: weeks })}
            >
              {weeks}w
            </button>
          ))}
        </div>
      </fieldset>

      <label className="promo-search">
        <span className="promo-search-label">{t("Search")}</span>
        <input
          type="search"
          value={scope.sku}
          placeholder={t("SKU, promo name, category")}
          onChange={(event) => onSearch(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="promo-button"
        onClick={onRefresh}
        disabled={busy}
      >
        {t("Refresh")}
      </button>
      {hasFilter ? (
        <button type="button" className="promo-button promo-button--quiet" onClick={onClear}>
          {t("Clear")}
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

function SelectField({ label, value, options, disabled, title, onChange }) {
  const { t } = useLanguage();
  return (
    <label className="promo-select" title={title}>
      <span className="promo-select-label">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
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
