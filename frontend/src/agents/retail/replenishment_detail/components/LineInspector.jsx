import DrillDrawer, { DrillSection } from "../../../../components/DrillDrawer.jsx";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { ELIGIBILITY_LABELS, EXCEPTION_LABELS } from "../data/contract.js";
import { formatIdrExact, formatPercent, formatUnits } from "../presentation.js";

/**
 * The selected-line inspector, spec section 8.3.
 *
 * Four sections in the spec's order: inventory basis, order conversion, vendor
 * comparison, execution. The first three are evidence; the fourth is the one
 * that has to say what is absent.
 */
export default function LineInspector({ inspector, onClose }) {
  const { t, language } = useLanguage();
  if (!inspector) return null;

  const { line, inventory, conversion, vendor, exceptions, eligibility, trace } =
    inspector;

  return (
    <DrillDrawer
      title={`${line.sku_id} · ${line.name}`}
      subtitle={`${line.category_label} · ${line.vertical_id}`}
      onClose={onClose}
    >
      <div className="rdet-inspector">
        <p className={`rdet-eligibility rdet-eligibility-${eligibility.toLowerCase()}`}>
          {t(ELIGIBILITY_LABELS[eligibility] || eligibility)}
        </p>

        {exceptions.length ? (
          <DrillSection icon="!" title="Exceptions" note="Why this line cannot be actioned.">
            <ul className="rdet-exception-list">
              {exceptions.map((code) => (
                <li key={code}>{t(EXCEPTION_LABELS[code] || code)}</li>
              ))}
            </ul>
          </DrillSection>
        ) : null}

        <DrillSection
          icon="1"
          title="Inventory basis"
          note="Position is reconstructed from on-hand and open PO, not stored."
        >
          <Rows rows={inventory} language={language} />
        </DrillSection>

        <DrillSection
          icon="2"
          title="Order conversion"
          note="Buy quantity rounds up to whole packs, so the order lands above the requirement."
        >
          <Rows rows={conversion} language={language} />
        </DrillSection>

        <DrillSection
          icon="3"
          title="Vendor comparison"
          note="Prices are per sales unit. Lowest price is not lowest landed cost."
        >
          <table className="rdet-quote-table">
            <thead>
              <tr>
                <th>{t("Vendor")}</th>
                <th className="num">{t("Unit price")}</th>
                <th className="num">{t("Min qty")}</th>
                <th>{t("Role")}</th>
              </tr>
            </thead>
            <tbody>
              {vendor.candidates.length ? (
                vendor.candidates.map((quote) => (
                  <tr
                    key={quote.vendor_account}
                    className={
                      quote.vendor === vendor.best ? "rdet-quote-best" : ""
                    }
                  >
                    <td>{quote.vendor}</td>
                    <td className="num">
                      {formatIdrExact(quote.unit_price, language)}
                    </td>
                    <td className="num">
                      {formatUnits(quote.min_qty_break, language)}
                    </td>
                    <td>{role(quote, vendor, t)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4}>{t("No quotes on file for this item.")}</td>
                </tr>
              )}
            </tbody>
          </table>

          <p className="rdet-saving-line">
            {vendor.saving > 0
              ? `${t("Switching to")} ${vendor.best} ${t("would save")} ${formatIdrExact(vendor.saving, language)} (${formatPercent(vendor.saving_pct, language)}) ${t("on this line")}.`
              : t("The designated vendor already holds the best price on file.")}
          </p>
          {vendor.terms ? (
            <p className="rdet-terms">
              {t("Agreement")}: {vendor.terms.currency} ·{" "}
              {t("valid")} {vendor.terms.valid_from} → {vendor.terms.valid_to} ·{" "}
              {t("lead")} {vendor.terms.lead_time_days}d
            </p>
          ) : null}
        </DrillSection>

        <DrillSection
          icon="4"
          title="Calculation trace"
          note="Every figure above, with this line's numbers substituted."
        >
          <ol className="rdet-trace">
            {trace.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </DrillSection>

        {/*
          Spec section 8.3 asks for an Execution section: selected vendor,
          approved quantity, override reason, PR/PO status, SoA status, ERP
          document. This dataset carries none of them (section 17, finding 7).
          Naming each missing field is the point — four empty boxes would read
          as data that failed to load rather than as a sheet that never held it.
        */}
        <DrillSection
          icon="5"
          title="Execution"
          note="Not connected in this dataset."
        >
          <p className="rdet-absent">
            {t(
              "This sheet is a recommendation snapshot, not an execution ledger. It carries no run id, approved quantity, override reason, requisition or PO status, SoA approval or ERP document number, so nothing here records whether this line was ordered.",
            )}
          </p>
        </DrillSection>
      </div>
    </DrillDrawer>
  );
}

function role(quote, vendor, t) {
  const parts = [];
  if (quote.vendor === vendor.designated) parts.push(t("Designated"));
  if (quote.vendor === vendor.best) parts.push(t("Best price"));
  return parts.join(" · ") || "—";
}

function Rows({ rows, language }) {
  return (
    <dl className="rdet-facts">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>
            {formatUnits(row.value, language)}
            {row.unit ? <span className="rdet-unit"> {row.unit}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
