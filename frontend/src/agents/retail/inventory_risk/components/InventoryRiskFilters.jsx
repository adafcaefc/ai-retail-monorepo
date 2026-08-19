import { useEffect, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { ALL } from "../data/contract.js";
import { SUPPORTS_STORE_SCOPE } from "../data/selectors.js";
import { stateSlug } from "../presentation.js";

function SelectField({ id, label, value, options, allLabel, disabled, title, onChange }) {
  return (
    <label className="risk-filter-field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={value}
        disabled={disabled}
        title={title}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value={ALL}>{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function InventoryRiskFilters({
  scope,
  options,
  horizonWeeks,
  busy,
  onPatch,
  onHorizon,
  onSearch,
  onRefresh,
  onClear,
}) {
  const { t } = useLanguage();
  const [search, setSearch] = useState(scope.sku);

  useEffect(() => setSearch(scope.sku), [scope.sku]);

  function submitSearch(event) {
    event.preventDefault();
    onSearch(search);
  }

  return (
    <section className="risk-filter-bar" aria-label={t("Inventory risk filters")}>
      <div className="risk-filter-selects">
        <SelectField
          id="risk-filter-entity"
          label={t("Legal entity")}
          value={scope.legal_entity_id}
          options={options.legal_entities}
          allLabel={t("All verticals")}
          onChange={(value) =>
            // A category or store from the previous vertical cannot exist
            // under the new one, so reset both rather than load an empty scope.
            onPatch({
              legal_entity_id: value,
              category_group: ALL,
              store_id: ALL,
            })
          }
        />
        <SelectField
          id="risk-filter-category"
          label={t("Category")}
          value={scope.category_group}
          options={options.categories}
          allLabel={t("All categories")}
          onChange={(value) => onPatch({ category_group: value })}
        />
        <SelectField
          id="risk-filter-store"
          label={t("Store")}
          value={scope.store_id}
          options={options.stores}
          allLabel={t("All stores")}
          disabled={!SUPPORTS_STORE_SCOPE}
          // Still keyed off the flag rather than always enabled: if a provider
          // ever cannot honour store scope, a disabled control that says why
          // beats one that silently changes nothing.
          title={
            SUPPORTS_STORE_SCOPE
              ? t("Shows this store's own position, not the chain's share of it.")
              : t("Store scope needs the per-store dataset, not yet available.")
          }
          onChange={(value) => {
            /*
             * A store implies its vertical, so a category from a different one
             * can only draw an empty board. Same reset the entity dropdown
             * above does, for the same reason — except the store list stays
             * chain-wide, so the reader can still jump straight to a store in
             * another vertical.
             */
            const store = options.stores.find((row) => row.value === value);
            const category = options.categories.find(
              (row) => row.value === scope.category_group,
            );
            const stale =
              store && category && category.legal_entity_id !== store.legal_entity_id;

            onPatch(
              stale
                ? { store_id: value, category_group: ALL }
                : { store_id: value },
            );
          }}
        />
      </div>

      <fieldset className="risk-state-filter">
        <legend>{t("State")}</legend>
        <div className="risk-segmented">
          <button
            type="button"
            aria-pressed={scope.state === ALL}
            onClick={() => onPatch({ state: ALL })}
          >
            {t("All")}
          </button>
          {options.states.map((state) => (
            <button
              key={state}
              type="button"
              className={`risk-chip risk-chip--${stateSlug(state)}`}
              aria-pressed={scope.state === state}
              onClick={() => onPatch({ state })}
            >
              {t(state)}
            </button>
          ))}
        </div>
      </fieldset>

      {/*
        A2 spec section 7a (`f-hz`): how far the projection runs. It sits with
        the filters because that is where the spec puts it, but it is passed
        separately from `scope` — it narrows no rows, and folding it into the
        scope would send it to a backend that has no use for it and would close
        the drill-down drawer, which describes a KPI's composition and does not
        depend on the horizon at all.

        The options come from the payload. A literal list here would be a
        second place for the board to disagree with itself about what it can
        compute.
      */}
      <fieldset className="risk-horizon-filter">
        <legend>{t("Horizon")}</legend>
        <div className="risk-segmented">
          {options.horizons_weeks.map((weeks) => (
            <button
              key={weeks}
              type="button"
              aria-pressed={horizonWeeks === weeks}
              onClick={() => onHorizon(weeks)}
            >
              {weeks}
              {t("w")}
            </button>
          ))}
        </div>
      </fieldset>

      <form className="risk-search" role="search" onSubmit={submitSearch}>
        <label htmlFor="risk-sku-search">{t("SKU search")}</label>
        <div>
          <input
            id="risk-sku-search"
            type="search"
            value={search}
            placeholder={t("Search SKU or item")}
            onChange={(event) => setSearch(event.target.value)}
          />
          <button type="submit">{t("Search")}</button>
        </div>
      </form>

      <div className="risk-filter-actions">
        <button
          type="button"
          className="risk-button"
          onClick={onRefresh}
          disabled={busy}
        >
          {busy ? t("Refreshing…") : t("Refresh")}
        </button>
        <button
          type="button"
          className="risk-button risk-button--quiet"
          onClick={onClear}
        >
          {t("Clear")}
        </button>
      </div>
    </section>
  );
}
