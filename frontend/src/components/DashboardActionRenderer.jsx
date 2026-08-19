import { useLanguage } from "../LanguageProvider.jsx";

// Mirrors the field labels/units already shown on the Demand Forecasting
// board itself (DemandForecastFilters.jsx's filter labels,
// DEMAND_LEVER_DEFINITIONS in agents/retail/demand_forecasting/data/
// contract.js for the levers) so a chat-applied change reads the same way
// here as it does on the board. Kept as a local, static map rather than an
// import so this renderer -- shared by every agent's chat -- stays
// agent-agnostic if another agent starts emitting dashboard_action blocks
// with a different field set.
const QUERY_FIELD_LABELS = {
  legal_entity_id: "Legal entity",
  category_group: "Category",
  store_id: "Store",
  sku: "SKU",
  grain: "Grain",
  horizon_weeks: "Horizon (weeks)",
};

const LEVER_LABELS = {
  demand: { label: "Demand shift", unit: "%" },
  promo: { label: "Promo intensity", unit: "%" },
  markdown: { label: "Markdown depth", unit: "%" },
  inbound: { label: "Extra inbound", unit: "%" },
  lead: { label: "Vendor lead time", unit: "d" },
  safety: { label: "Safety stock", unit: "d" },
};

function signed(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number > 0 ? `+${number}` : String(number);
}

export default function DashboardActionRenderer({ data }) {
  const { t } = useLanguage();
  if (!data) return null;

  const queryChanges = Object.entries(data.query || {}).filter(([, value]) => value != null && value !== "");
  const leverChanges = Object.entries(data.levers || {}).filter(([, value]) => value != null);
  const ranScenario = Boolean(data.run_scenario);

  if (!data.title && !data.summary && !queryChanges.length && !leverChanges.length) return null;

  return (
    <section className="dashboard-action-block">
      <h2 className="dashboard-action-title">{data.title || t("Applied to dashboard")}</h2>
      {data.summary ? <p className="dashboard-action-summary">{data.summary}</p> : null}

      {queryChanges.length || leverChanges.length ? (
        <ul className="dashboard-action-changes">
          {queryChanges.map(([key, value]) => (
            <li key={`query-${key}`}>
              <span>{t(QUERY_FIELD_LABELS[key] || key)}</span>
              <b>{String(value)}</b>
            </li>
          ))}
          {leverChanges.map(([key, value]) => {
            const definition = LEVER_LABELS[key];
            return (
              <li key={`lever-${key}`}>
                <span>{t(definition?.label || key)}</span>
                <b>{signed(value)}{definition?.unit || ""}</b>
              </li>
            );
          })}
        </ul>
      ) : null}

      {ranScenario ? (
        <span className="dashboard-action-badge">{t("Scenario run on the dashboard")}</span>
      ) : null}
    </section>
  );
}
