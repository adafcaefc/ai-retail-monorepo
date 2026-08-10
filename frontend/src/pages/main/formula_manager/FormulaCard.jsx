import { useCallback, useMemo, useState } from "react";

import { evaluateFormula } from "../../../api/formulas.js";
import { excelAddressHref, splitAddress } from "./excelAddress.js";
import { formatResult } from "./formatResult.js";
import ValidatePanel from "./ValidatePanel.jsx";
import workedExamples from "./workedExamples.json";

function defaultValues(formula) {
  const values = {};
  for (const parameter of formula.parameters || []) {
    values[parameter.key] = parameter.default ?? "";
  }
  return values;
}

/**
 * One formula: what it computes, the five workbook examples it was verified
 * against, and the validator those examples feed.
 */
export default function FormulaCard({ formula, onEdit, onDelete, deleting }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() => defaultValues(formula));
  const [active, setActive] = useState(null);
  const [result, setResult] = useState(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Worked examples are hardcoded reference data, not part of the store, so
  // they are never touched by CRUD.
  const examples = useMemo(
    () => workedExamples[formula.id] || [],
    [formula.id]
  );

  const clearRun = useCallback(() => {
    setResult(undefined);
    setError("");
  }, []);

  const loadExample = useCallback(
    (example) => {
      setOpen(true);
      setActive(example);
      setValues({ ...defaultValues(formula), ...example.values });
      clearRun();
    },
    [formula, clearRun]
  );

  const reset = useCallback(() => {
    setActive(null);
    setValues(defaultValues(formula));
    clearRun();
  }, [formula, clearRun]);

  const change = useCallback(
    (key, value) => {
      // Hand-editing means the run is no longer that example's run, but the
      // expected value stays on screen so the comparison keeps its meaning.
      setValues((previous) => ({ ...previous, [key]: value }));
      clearRun();
    },
    [clearRun]
  );

  const run = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const payload = await evaluateFormula(formula.id, values);
      setResult(payload.result);
    } catch (runError) {
      setResult(undefined);
      setError(runError.message || "Could not evaluate this formula.");
    } finally {
      setBusy(false);
    }
  }, [formula.id, values]);

  return (
    <article className="formula-card" data-testid={`formula-${formula.id}`}>
      <header className="formula-card-head">
        <div className="formula-card-title">
          <span className="formula-number" aria-hidden="true">
            {formula.number}
          </span>
          <div>
            <h3>{formula.name}</h3>
            {formula.logic ? <p>{formula.logic}</p> : null}
          </div>
        </div>

        <div className="formula-card-actions">
          <button
            type="button"
            className={"alerts-btn" + (open ? " on" : "")}
            aria-expanded={open}
            onClick={() => setOpen((previous) => !previous)}
          >
            {open ? "Hide validator" : "Validate"}
          </button>
          <button
            type="button"
            className="alerts-mini-btn"
            onClick={() => onEdit(formula)}
          >
            Edit
          </button>
          {confirming ? (
            <>
              <button
                type="button"
                className="alerts-mini-btn danger"
                disabled={deleting}
                onClick={() => onDelete(formula)}
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                type="button"
                className="alerts-mini-btn"
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              className="alerts-mini-btn"
              onClick={() => setConfirming(true)}
            >
              Delete
            </button>
          )}
        </div>
      </header>

      <pre className="info-card-formula formula-expression">
        {formula.expression}
      </pre>

      {examples.length > 0 ? (
        <div className="formula-try">
          <h4>Try this</h4>
          <p className="formula-try-hint">
            Five worked examples from the verification pack. Pick one to load
            its inputs into the validator.
          </p>
          <ul className="formula-examples">
            {examples.map((example) => {
              const { sheet, cell } = splitAddress(example.address);
              const selected = active?.address === example.address;
              return (
                <li key={example.address}>
                  <button
                    type="button"
                    className={
                      "formula-example" + (selected ? " selected" : "")
                    }
                    onClick={() => loadExample(example)}
                  >
                    <span className="formula-example-label">
                      {example.label}
                    </span>
                    <span className="formula-example-result">
                      {formatResult(example.expected)}
                    </span>
                  </button>
                  <a
                    className="formula-example-address"
                    href={excelAddressHref(example.address)}
                    title={`Open ${example.address} in the workbook`}
                  >
                    <span className="formula-example-sheet">{sheet}</span>
                    {sheet ? "!" : ""}
                    {cell}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {open ? (
        <ValidatePanel
          formula={formula}
          values={values}
          onChange={change}
          onRun={run}
          onReset={reset}
          busy={busy}
          result={result}
          error={error}
          expected={active ? active.expected : undefined}
          exampleLabel={active ? active.label : ""}
        />
      ) : null}
    </article>
  );
}
