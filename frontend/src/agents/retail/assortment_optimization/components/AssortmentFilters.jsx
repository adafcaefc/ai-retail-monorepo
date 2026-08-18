import { ALL, CLASSIFICATIONS } from "../data/contract.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

/**
 * The top filter row: vertical, category, assortment verdict, and a
 * free-text search across SKU, name, vendor and brand.
 */
export default function AssortmentFilters({
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
    scope.classification !== ALL ||
    (scope.sku && scope.sku.trim());

  return (
    <div className="assortment-filters" data-testid="assortment-filters">
      <SelectField
        label={t("Vertical")}
        value={scope.legal_entity_id}
        options={options.legal_entities}
        disabled={busy}
        onChange={(value) => onPatch({ legal_entity_id: value, category_group: ALL })}
      />
      <SelectField
        label={t("Category")}
        value={scope.category_group}
        options={categoriesInScope(options.categories, scope.legal_entity_id)}
        disabled={busy}
        onChange={(value) => onPatch({ category_group: value })}
      />
      <SelectField
        label={t("Verdict")}
        value={scope.classification}
        options={CLASSIFICATIONS.map((c) => ({ value: c, label: t(VERDICT_LABELS[c]) }))}
        disabled={busy}
        onChange={(value) => onPatch({ classification: value })}
      />
      <label className="assortment-search">
        <span className="assortment-search-label">{t("Search")}</span>
        <input
          type="search"
          value={scope.sku}
          placeholder={t("SKU, name, vendor, brand")}
          onChange={(event) => onSearch(event.target.value)}
        />
      </label>
      <button type="button" className="assortment-button" onClick={onRefresh} disabled={busy}>
        {t("Refresh")}
      </button>
      {hasFilter ? (
        <button type="button" className="assortment-button" onClick={onClear}>
          {t("Clear all")}
        </button>
      ) : null}
    </div>
  );
}

const VERDICT_LABELS = {
  delist: "Delist",
  grow: "Grow",
  hold: "Hold",
};

function categoriesInScope(categories, vertical) {
  if (!vertical || vertical === ALL) return categories;
  return categories.filter((c) => c.legal_entity_id === vertical);
}

function SelectField({ label, value, options, disabled, onChange }) {
  const { t } = useLanguage();
  return (
    <label className="assortment-select">
      <span className="assortment-select-label">{label}</span>
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
