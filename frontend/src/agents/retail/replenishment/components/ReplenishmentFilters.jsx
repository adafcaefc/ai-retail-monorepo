import { useEffect, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { ALL } from "../data/contract.js";

/** A3 spec section 8a: the filters every visual on the page obeys. */
export default function ReplenishmentFilters({
  scope,
  options,
  busy,
  onPatch,
  onSearch,
  onClear,
}) {
  const { t } = useLanguage();
  const [term, setTerm] = useState(scope.sku);

  useEffect(() => setTerm(scope.sku), [scope.sku]);

  return (
    <form
      className="po-filters"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(term);
      }}
    >
      <label>
        <span>{t("Legal entity")}</span>
        <select
          value={scope.legal_entity_id}
          disabled={busy}
          onChange={(event) =>
            onPatch({
              legal_entity_id: event.target.value,
              category_group: ALL,
              store_id: ALL,
            })
          }
        >
          <option value={ALL}>{t("All")}</option>
          {options.legal_entities.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>{t("Category")}</span>
        <select
          value={scope.category_group}
          disabled={busy}
          onChange={(event) => onPatch({ category_group: event.target.value })}
        >
          <option value={ALL}>{t("All")}</option>
          {options.categories.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>{t("Route")}</span>
        <select
          value={scope.route}
          disabled={busy}
          onChange={(event) => onPatch({ route: event.target.value })}
        >
          <option value={ALL}>{t("All")}</option>
          {options.routes.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="po-search">
        <span>{t("SKU search")}</span>
        <input
          type="search"
          value={term}
          disabled={busy}
          placeholder={t("Code or name")}
          onChange={(event) => setTerm(event.target.value)}
        />
      </label>

      {/*
        Default on. A buyer opening this board wants today's order, not an
        inventory report — but the fill-rate KPI needs the whole assortment as
        its denominator, so the toggle has to exist rather than the filter
        being hard-wired.
      */}
      <label className="po-toggle">
        <input
          type="checkbox"
          checked={scope.reorder_only}
          disabled={busy}
          onChange={(event) => onPatch({ reorder_only: event.target.checked })}
        />
        <span>{t("Only what needs ordering")}</span>
      </label>

      <div className="po-filter-actions">
        <button type="submit" className="po-button" disabled={busy}>
          {t("Search")}
        </button>
        <button
          type="button"
          className="po-button po-button--quiet"
          onClick={onClear}
          disabled={busy}
        >
          {t("Clear all")}
        </button>
      </div>
    </form>
  );
}
