import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * The What-If simulator — A6 spec section 9c. `markdown` is listed but
 * inert (modelled: false): the workbook's formula set has no depth term.
 *
 * Draft levers vs applied levers: the sliders hold draft, "Run" applies.
 * Moving a slider is an assumption, never a result.
 */
export default function AssortmentWhatIfSimulator({
  simulation,
  draftLevers,
  onLeverChange,
  onRun,
  onReset,
  onSave,
  driveWholePage,
  onDriveWholePageChange,
  canSave,
  busy,
}) {
  const { t } = useLanguage();
  const index = simulation?.index ?? [];

  return (
    <section className="assortment-simulator" data-testid="assortment-simulator">
      <header className="assortment-section-head">
        <h3>{t("What-If simulator")}</h3>
        <label className="assortment-drive-toggle">
          <input
            type="checkbox"
            checked={driveWholePage}
            onChange={(event) => onDriveWholePageChange(event.target.checked)}
          />
          {t("Drive whole page")}
        </label>
      </header>

      <div className="assortment-levers">
        {LEVER_DEFINITIONS.map((lever) => (
          <label
            key={lever.id}
            className={`assortment-lever${lever.modelled === false ? " is-inert" : ""}`}
          >
            <span className="assortment-lever-label">
              {t(lever.label)}
              <em className="assortment-lever-cell">{lever.cell}</em>
            </span>
            <span className="assortment-lever-effect">{t(lever.effect)}</span>
            <span className="assortment-lever-control">
              <input
                type="range"
                min={lever.min}
                max={lever.max}
                step={lever.step}
                value={Number(draftLevers?.[lever.id] ?? 0)}
                disabled={busy}
                onChange={(event) => onLeverChange(lever.id, Number(event.target.value))}
              />
              <output>
                {draftLevers?.[lever.id] ?? 0}
                {lever.unit}
              </output>
            </span>
          </label>
        ))}
      </div>

      <div className="assortment-simulator-actions">
        <button type="button" className="assortment-button" onClick={onRun} disabled={busy}>
          {t("Run")}
        </button>
        <button type="button" className="assortment-button" onClick={onReset} disabled={busy}>
          {t("Reset")}
        </button>
        <button
          type="button"
          className="assortment-button"
          onClick={onSave}
          disabled={!canSave || busy}
          title={!canSave ? t("Move a lever and Run, then save") : ""}
        >
          {t("Save scenario")}
        </button>
      </div>

      <div className="assortment-simulator-chart">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={index} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, "auto"]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="baseline_index" name={t("Baseline")} fill="var(--gray-400)" />
            <Bar dataKey="scenario_index" name={t("Scenario")} fill="var(--blue-500)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
