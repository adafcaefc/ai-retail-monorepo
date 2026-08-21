import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { useMemo, useState } from "react";
import {
  DEFAULT_FORECAST_DETAIL_SORT,
  sortForecastDetailRows,
  toggleForecastDetailSort,
} from "../data/forecastDetailSorting.js";

const GRAIN_LABELS = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

const SORT_LABELS = {
  sku: "SKU",
  category: "Category",
  ads: "ADS",
  forecast: "Forecast",
  trend: "Trend",
  signals: "Signals",
  supply_state: "Supply state",
};

function SortHeader({ column, label, numeric, sort, onSort, t }) {
  const active = sort.column === column;
  const direction = active ? sort.direction : null;
  const directionLabel = direction === "asc" ? "ascending" : "descending";
  const ariaDirection = direction === "asc" ? "ascending" : "descending";

  return (
    <th
      className={numeric ? "num" : undefined}
      scope="col"
      aria-sort={active ? ariaDirection : "none"}
    >
      <button
        type="button"
        className="demand-detail-sort-button"
        aria-label={`${t("Sort by")} ${label}`}
        title={`${t("Sort by")} ${label}`}
        onClick={() => onSort(column)}
      >
        <span>{label}</span>
        <span className="demand-detail-sort-indicator" aria-hidden="true">
          {active ? (direction === "asc" ? "▲" : "▼") : ""}
        </span>
        {active ? <span className="demand-detail-sort-direction">{directionLabel}</span> : null}
      </button>
    </th>
  );
}

export default function ForecastDetailTable({ details, grain, onSelect, onAskInsight, askBusy }) {
  const { language, t } = useLanguage();
  const [sort, setSort] = useState(DEFAULT_FORECAST_DETAIL_SORT);
  const rows = useMemo(
    () => sortForecastDetailRows(details.rows, sort),
    [details.rows, sort],
  );
  const sortLabel = ["sku", "ads"].includes(sort.column)
    ? t(SORT_LABELS[sort.column])
    : t(SORT_LABELS[sort.column]).toLowerCase();
  const sortDirection = t(sort.direction === "asc" ? "ascending" : "descending");

  const handleSort = (column) => {
    setSort((current) => toggleForecastDetailSort(current, column));
  };

  return (
    <section className="demand-panel demand-detail-panel" aria-labelledby="demand-detail-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("SKU-level view")}</p>
          <h2 id="demand-detail-title">{t("Forecast detail")}</h2>
          <span>{t("Sorted by")} {sortLabel} {sortDirection} · {formatNumber(details.total, language, { maximumFractionDigits: 0 })} {t("matches")}</span>
        </div>
        <span className="demand-panel-tag">{t(GRAIN_LABELS[grain])}</span>
      </header>
      {rows.length ? (
        <div className="demand-detail-scroll">
          <table>
            <thead>
              <tr>
                <SortHeader column="sku" label={t("SKU")} sort={sort} onSort={handleSort} t={t} />
                <SortHeader column="category" label={t("Category")} sort={sort} onSort={handleSort} t={t} />
                <SortHeader column="ads" label="ADS" numeric sort={sort} onSort={handleSort} t={t} />
                <SortHeader
                  column="forecast"
                  label={`${t(GRAIN_LABELS[grain])} ${t("Forecast")}`}
                  numeric
                  sort={sort}
                  onSort={handleSort}
                  t={t}
                />
                <SortHeader column="trend" label={t("Trend")} numeric sort={sort} onSort={handleSort} t={t} />
                <SortHeader column="signals" label={t("Signals")} sort={sort} onSort={handleSort} t={t} />
                <SortHeader column="supply_state" label={t("Supply state")} sort={sort} onSort={handleSort} t={t} />
                <th scope="col">{t("Ask AI")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.sku_id}>
                  <td>
                    <button type="button" className="demand-sku-link" onClick={() => onSelect(row.sku_id)}>
                      <strong>{row.sku_name}</strong>
                      <span>{row.sku_id}</span>
                    </button>
                  </td>
                  <td>{row.category_label}</td>
                  <td className="num">{formatNumber(row.ads_units_per_day, language, { maximumFractionDigits: 1 })}</td>
                  <td className="num strong">{formatNumber(row.forecast_units, language, { maximumFractionDigits: 0 })}</td>
                  <td className={`num ${row.trend_pct >= 0 ? "positive" : "negative"}`}>
                    {row.trend_pct > 0 ? "+" : ""}{formatNumber(row.trend_pct, language, { maximumFractionDigits: 1 })}%
                  </td>
                  <td><span className="demand-signal-list">{row.signals.length ? row.signals.map((signal) => <i key={signal}>{t(signal)}</i>) : "—"}</span></td>
                  <td><span className={`demand-supply demand-supply--${row.supply_state.toLowerCase()}`}>{t(row.supply_state)}</span></td>
                  <td>
                    <button
                      type="button"
                      className="row-ask-ai-btn"
                      disabled={askBusy}
                      onClick={() => onAskInsight?.({ row: forecastRowInsight(row, grain, t) })}
                    >
                      {t("Ask AI")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="workboard-empty">{t("No SKUs match the current scope.")}</p>}
    </section>
  );
}

function forecastRowInsight(row, grain, t) {
  return {
    title: `${row.sku_name} (${row.sku_id})`,
    fields: [
      { label: t("Category"), value: row.category_label },
      { label: "ADS", value: row.ads_units_per_day },
      { label: `${t(GRAIN_LABELS[grain])} ${t("Forecast")}`, value: row.forecast_units },
      { label: t("Trend"), value: `${row.trend_pct > 0 ? "+" : ""}${row.trend_pct}%` },
      { label: t("Signals"), value: row.signals.length ? row.signals.map((signal) => t(signal)).join(", ") : "—" },
      { label: t("Supply state"), value: t(row.supply_state) },
    ],
  };
}
