import { excelAddressHref } from "../../excelAddress.js";
import { formatResult, resultsMatch } from "./formatResult.js";

/**
 * The tweakable-parameter form. Fully controlled by FormulaCard so that
 * clicking a worked example can drop its values straight in.
 *
 * `sources` is the loaded example's cell citations, one per parameter. It is
 * absent until an example is picked, and for a user-created formula there is
 * no example to pick -- so every input renders with or without it.
 */
export default function ValidatePanel({
  formula,
  values,
  onChange,
  onRun,
  onReset,
  busy,
  result,
  error,
  expected,
  exampleLabel,
  sources
}) {
  const parameters = formula.parameters || [];
  const matched = expected === undefined ? null : resultsMatch(result, expected);

  return (
    <div className="formula-validate">
      <div className="formula-validate-head">
        <h4>Parameters</h4>
        {exampleLabel ? (
          <p className="formula-validate-source">
            Loaded from <strong>{exampleLabel}</strong>
          </p>
        ) : (
          <p className="formula-validate-source">
            Starting from each parameter&rsquo;s default.
          </p>
        )}
      </div>

      {parameters.length === 0 ? (
        <p className="alerts-empty">This formula has no parameters.</p>
      ) : (
        <div className="formula-params">
          {parameters.map((parameter) => {
            const address = sources?.[parameter.key];
            return (
              // The citation sits outside the <label> deliberately: a link
              // inside one also fires the label's activation and steals focus
              // to the input on its way to the worksheet.
              <div className="formula-param-field" key={parameter.key}>
                <label className="formula-param">
                  <span className="formula-param-label">
                    {parameter.label}
                  </span>
                  <input
                    type={parameter.type === "number" ? "number" : "text"}
                    step="any"
                    value={values[parameter.key] ?? ""}
                    aria-label={parameter.label}
                    onChange={(event) =>
                      onChange(parameter.key, event.target.value)
                    }
                  />
                </label>
                <div className="formula-param-foot">
                  <span className="formula-param-key">{parameter.key}</span>
                  {address ? (
                    <a
                      className="formula-param-cell"
                      href={excelAddressHref(address)}
                      title={`Open ${address} in the workbook`}
                    >
                      {address}
                    </a>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="formula-validate-actions">
        <button
          type="button"
          className="alerts-btn primary"
          onClick={onRun}
          disabled={busy}
        >
          {busy ? "Running…" : "Run"}
        </button>
        <button
          type="button"
          className="alerts-btn"
          onClick={onReset}
          disabled={busy}
        >
          Reset
        </button>
      </div>

      {error ? (
        <p className="alerts-error" role="alert">
          {error}
        </p>
      ) : null}

      {result !== undefined && result !== null && !error ? (
        <div className="formula-result" data-testid="formula-result">
          <div className="formula-result-row">
            <span className="formula-result-label">Computed</span>
            <strong className="formula-result-value">
              {formatResult(result)}
            </strong>
          </div>
          {expected === undefined ? null : (
            <>
              <div className="formula-result-row">
                <span className="formula-result-label">Workbook</span>
                <strong className="formula-result-value">
                  {formatResult(expected)}
                </strong>
              </div>
              <span
                className={
                  "status-pill " + (matched ? "status-approved" : "status-planned")
                }
              >
                {matched ? "Matches workbook" : "Differs from workbook"}
              </span>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
