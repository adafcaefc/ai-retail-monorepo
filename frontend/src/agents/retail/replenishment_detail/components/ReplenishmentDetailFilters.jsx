import { useEffect, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { ALL, REORDER_STATUS, ELIGIBILITY_LABELS } from "../data/contract.js";

/**
 * The ten filters of spec section 9.
 *
 * TWO KINDS, AND THE DIFFERENCE IS INVISIBLE ON SCREEN. Vertical and Category
 * round-trip to the backend and narrow the SQL. The other eight narrow rows
 * already on the page, in `selectors.js`. Nothing here needs to know which is
 * which — `serializeScope` in contract.js decides what travels — but the split
 * is why this board never sends `buy_uom`: it is not a field of
 * `DashboardScope`, and the dashboard route answers an unknown filter with a
 * 400 rather than dropping it.
 *
 * Search is a submit form rather than a keystroke handler. Pricing & Markdown
 * filters on every keypress, which is fine over its candidate list; this grid
 * re-sorts 800 rows, and doing that per character is visible.
 */
export default function ReplenishmentDetailFilters({
  scope,
  options,
  busy,
  onPatch,
  onSearch,
  onRefresh,
  onClear,
}) {
  const { t } = useLanguage();
  const [term, setTerm] = useState(scope.sku || "");

  // Keeps the box in step when the scope is cleared from anywhere else.
  useEffect(() => {
    setTerm(scope.sku || "");
  }, [scope.sku]);

  // Categories belong to a vertical, so offering all of them under a chosen
  // vertical offers rows that cannot exist.
  const categoriesInScope = (options.categories || []).filter(
    (option) =>
      scope.legal_entity_id === ALL ||
      option.legal_entity_id === scope.legal_entity_id,
  );

  const dirty =
    scope.legal_entity_id !== ALL ||
    scope.category_group !== ALL ||
    scope.reorder_status !== "YES" ||
    scope.designated_vendor !== ALL ||
    scope.best_price_vendor !== ALL ||
    scope.buy_uom !== ALL ||
    scope.eligibility !== ALL ||
    scope.saving_only ||
    scope.min_amount !== "" ||
    scope.max_amount !== "" ||
    Boolean(scope.sku);

  return (
    <div className="rdet-filters" data-testid="replenishment-detail-filters">
      <SelectField
        label={t("Vertical")}
        value={scope.legal_entity_id}
        options={options.legal_entities || []}
        disabled={busy}
        // Changing vertical strands any category chosen under the old one.
        onChange={(value) =>
          onPatch({ legal_entity_id: value, category_group: ALL })
        }
      />
      <SelectField
        label={t("Category")}
        value={scope.category_group}
        options={categoriesInScope}
        disabled={busy}
        onChange={(value) => onPatch({ category_group: value })}
      />
      <SelectField
        label={t("Reorder status")}
        value={scope.reorder_status}
        options={REORDER_STATUS}
        disabled={busy}
        allLabel={null}
        onChange={(value) => onPatch({ reorder_status: value })}
      />
      <SelectField
        label={t("Designated vendor")}
        value={scope.designated_vendor}
        options={options.vendors || []}
        disabled={busy}
        onChange={(value) => onPatch({ designated_vendor: value })}
      />
      <SelectField
        label={t("Best-price vendor")}
        value={scope.best_price_vendor}
        options={options.best_price_vendors || []}
        disabled={busy}
        onChange={(value) => onPatch({ best_price_vendor: value })}
      />
      <SelectField
        label={t("Buy UOM")}
        value={scope.buy_uom}
        options={options.buy_uoms || []}
        disabled={busy}
        onChange={(value) => onPatch({ buy_uom: value })}
      />
      <SelectField
        label={t("Eligibility")}
        value={scope.eligibility}
        options={Object.entries(ELIGIBILITY_LABELS).map(([value, label]) => ({
          value,
          label: t(label),
        }))}
        disabled={busy}
        onChange={(value) => onPatch({ eligibility: value })}
      />

      <label className="rdet-field rdet-field-amount">
        <span>{t("Amount band")}</span>
        <span className="rdet-band">
          <input
            type="number"
            inputMode="numeric"
            placeholder={t("Min")}
            value={scope.min_amount}
            disabled={busy}
            aria-label={t("Minimum amount")}
            onChange={(event) => onPatch({ min_amount: event.target.value })}
          />
          <input
            type="number"
            inputMode="numeric"
            placeholder={t("Max")}
            value={scope.max_amount}
            disabled={busy}
            aria-label={t("Maximum amount")}
            onChange={(event) => onPatch({ max_amount: event.target.value })}
          />
        </span>
      </label>

      <form
        className="rdet-field rdet-field-search"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch(term);
        }}
      >
        <label htmlFor="rdet-search">{t("Item search")}</label>
        <span className="rdet-search-row">
          <input
            id="rdet-search"
            type="search"
            placeholder={t("Item code or name")}
            value={term}
            disabled={busy}
            onChange={(event) => setTerm(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {t("Search")}
          </button>
        </span>
      </form>

      <label className="rdet-check">
        <input
          type="checkbox"
          checked={Boolean(scope.saving_only)}
          disabled={busy}
          onChange={(event) => onPatch({ saving_only: event.target.checked })}
        />
        <span>{t("Savings opportunity only")}</span>
      </label>

      <div className="rdet-filter-actions">
        <button type="button" onClick={onRefresh} disabled={busy}>
          {t("Refresh")}
        </button>
        {dirty ? (
          <button type="button" onClick={onClear} disabled={busy}>
            {t("Clear all")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A select that prepends its own "All" option.
 *
 * `allLabel: null` suppresses it, for the reorder-status control — that one is
 * a three-way choice in which "All lines" is already one of the values, and a
 * second all-option would be a different way of saying the same thing.
 */
function SelectField({
  label,
  value,
  options,
  disabled,
  onChange,
  allLabel = "All",
}) {
  const { t } = useLanguage();
  const items =
    allLabel === null
      ? options
      : [{ value: ALL, label: t(allLabel) }, ...options];

  return (
    <label className="rdet-field">
      <span>{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {items.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
