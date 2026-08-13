import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

const GRAIN_LABELS = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

export default function ForecastDetailTable({ details, grain, onSelect }) {
  const { language, t } = useLanguage();
  return (
    <section className="demand-panel demand-detail-panel" aria-labelledby="demand-detail-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("SKU-level view")}</p>
          <h2 id="demand-detail-title">{t("Forecast detail")}</h2>
          <span>{t("Sorted by forecast descending")} · {formatNumber(details.total, language, { maximumFractionDigits: 0 })} {t("matches")}</span>
        </div>
        <span className="demand-panel-tag">{t(GRAIN_LABELS[grain])}</span>
      </header>
      {details.rows.length ? (
        <div className="demand-detail-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("SKU")}</th>
                <th>{t("Category")}</th>
                <th className="num">ADS</th>
                <th className="num">{t(GRAIN_LABELS[grain])} {t("Forecast")}</th>
                <th className="num">{t("Trend")}</th>
                <th>{t("Signals")}</th>
                <th>{t("Supply state")}</th>
              </tr>
            </thead>
            <tbody>
              {details.rows.map((row) => (
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="workboard-empty">{t("No SKUs match the current scope.")}</p>}
    </section>
  );
}
