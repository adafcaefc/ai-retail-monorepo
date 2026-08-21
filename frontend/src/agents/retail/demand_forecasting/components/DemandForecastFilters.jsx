import { useEffect, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";

function SelectField({ label, value, options, allLabel, onChange }) {
  return (
    <label className="demand-filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="ALL">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function DemandForecastFilters({
  query,
  options,
  busy,
  onPatch,
  onSearch,
  onRefresh,
  onClear,
}) {
  const { t } = useLanguage();
  const [search, setSearch] = useState(query.sku);

  useEffect(() => setSearch(query.sku), [query.sku]);

  function submitSearch(event) {
    event.preventDefault();
    onSearch(search);
  }

  function changeCategory(category_group) {
    const selectedStore = options.stores.find((option) => option.value === query.store_id);
    const storeRemainsValid = query.store_id === "ALL"
      || category_group === "ALL"
      || !Array.isArray(selectedStore?.category_ids)
      || selectedStore.category_ids.includes(category_group);

    onPatch({
      category_group,
      ...(storeRemainsValid ? {} : { store_id: "ALL" }),
    });
  }

  return (
    <section className="demand-filter-bar" aria-label={t("Demand forecast filters")}>
      <div className="demand-filter-selects">
        <SelectField
          label={t("Legal entity")}
          value={query.legal_entity_id}
          options={options.legal_entities}
          allLabel={t("All verticals")}
          onChange={(value) => onPatch({
            legal_entity_id: value,
            category_group: "ALL",
            store_id: "ALL",
          })}
        />
        <SelectField
          label={t("Category")}
          value={query.category_group}
          options={options.categories}
          allLabel={t("All categories")}
          onChange={changeCategory}
        />
        <SelectField
          label={t("Store")}
          value={query.store_id}
          options={options.stores}
          allLabel={t("All stores")}
          onChange={(value) => onPatch({ store_id: value })}
        />
      </div>

      <fieldset className="demand-horizon">
        <legend>{t("Horizon")}</legend>
        <div className="demand-segmented">
          {options.horizons_weeks.map((weeks) => (
            <button
              key={weeks}
              type="button"
              aria-pressed={query.horizon_weeks === weeks}
              onClick={() => onPatch({ horizon_weeks: weeks })}
            >
              {weeks}w
            </button>
          ))}
        </div>
      </fieldset>

      <form className="demand-search" role="search" onSubmit={submitSearch}>
        <label htmlFor="demand-sku-search">{t("SKU search")}</label>
        <div>
          <input
            id="demand-sku-search"
            type="search"
            value={search}
            placeholder={t("Search SKU or item")}
            onChange={(event) => setSearch(event.target.value)}
          />
          <button type="submit">{t("Search")}</button>
        </div>
      </form>

      <div className="demand-filter-actions">
        <button type="button" className="demand-button" onClick={onRefresh} disabled={busy}>
          {busy ? t("Refreshing…") : t("Refresh")}
        </button>
        <button type="button" className="demand-button demand-button--quiet" onClick={onClear}>
          {t("Clear")}
        </button>
      </div>
    </section>
  );
}
