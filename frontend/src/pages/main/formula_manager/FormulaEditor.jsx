import { useCallback, useEffect, useState } from "react";

import Modal from "../../../components/Modal.jsx";
import { validateFormula } from "../../../api/formulas.js";

const EMPTY = {
  name: "",
  logic: "",
  sheet: "",
  result_type: "number",
  expression: "",
  parameters: []
};

function toDraft(formula) {
  if (!formula) {
    return { ...EMPTY, parameters: [] };
  }
  return {
    name: formula.name || "",
    logic: formula.logic || "",
    sheet: formula.sheet || "",
    result_type: formula.result_type || "number",
    expression: formula.expression || "",
    parameters: (formula.parameters || []).map((parameter) => ({
      key: parameter.key,
      label: parameter.label,
      type: parameter.type || "number",
      default: parameter.default ?? ""
    }))
  };
}

/** Create or edit a formula, with the backend validating as you type. */
export default function FormulaEditor({ formula, onCancel, onSave, saving }) {
  const [draft, setDraft] = useState(() => toDraft(formula));
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  const setField = useCallback((field, value) => {
    setDraft((previous) => ({ ...previous, [field]: value }));
  }, []);

  // One validator, server-side, so the editor cannot disagree with what the
  // save endpoint will accept. Debounced so a keystroke is not a request.
  useEffect(() => {
    if (!draft.expression.trim()) {
      setReport(null);
      return undefined;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const payload = await validateFormula(
          draft.expression,
          draft.parameters
        );
        if (!cancelled) {
          setReport(payload);
        }
      } catch {
        // A validation outage must not block typing; save still guards.
        if (!cancelled) {
          setReport(null);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [draft.expression, draft.parameters]);

  const addParameter = useCallback(() => {
    setDraft((previous) => ({
      ...previous,
      parameters: [
        ...previous.parameters,
        { key: "", label: "", type: "number", default: "" }
      ]
    }));
  }, []);

  const changeParameter = useCallback((index, field, value) => {
    setDraft((previous) => ({
      ...previous,
      parameters: previous.parameters.map((parameter, position) =>
        position === index ? { ...parameter, [field]: value } : parameter
      )
    }));
  }, []);

  const removeParameter = useCallback((index) => {
    setDraft((previous) => ({
      ...previous,
      parameters: previous.parameters.filter(
        (_, position) => position !== index
      )
    }));
  }, []);

  const submit = useCallback(
    async (event) => {
      event.preventDefault();
      setError("");
      try {
        await onSave({
          ...draft,
          name: draft.name.trim(),
          parameters: draft.parameters.map((parameter) => ({
            ...parameter,
            key: parameter.key.trim(),
            label: parameter.label.trim() || parameter.key.trim(),
            default: parameter.default === "" ? null : parameter.default
          }))
        });
      } catch (saveError) {
        setError(saveError.message || "Could not save this formula.");
      }
    },
    [draft, onSave]
  );

  const invalid = report ? !report.valid : false;
  const blocked = saving || invalid || !draft.name.trim() || !draft.expression.trim();

  return (
    <Modal
      title={formula ? `Edit ${formula.name}` : "New formula"}
      subtitle="Expressions use named parameters — no Excel cell references."
      onClose={onCancel}
      wide
    >
      <form className="formula-editor" onSubmit={submit}>
        <div className="formula-field-row">
          <label className="formula-field">
            <span>Name</span>
            <input
              value={draft.name}
              onChange={(event) => setField("name", event.target.value)}
              required
            />
          </label>
          <label className="formula-field">
            <span>Sheet</span>
            <input
              value={draft.sheet}
              onChange={(event) => setField("sheet", event.target.value)}
              placeholder="ENGINE_STORE"
            />
          </label>
          <label className="formula-field">
            <span>Result type</span>
            <select
              value={draft.result_type}
              onChange={(event) => setField("result_type", event.target.value)}
            >
              <option value="number">number</option>
              <option value="text">text</option>
            </select>
          </label>
        </div>

        <label className="formula-field">
          <span>Documented logic</span>
          <input
            value={draft.logic}
            onChange={(event) => setField("logic", event.target.value)}
            placeholder="Plain-language description"
          />
        </label>

        <label className="formula-field">
          <span>Expression</span>
          <textarea
            className="formula-expression-input"
            rows={4}
            value={draft.expression}
            spellCheck={false}
            onChange={(event) => setField("expression", event.target.value)}
            required
          />
        </label>

        {report && report.errors.length > 0 ? (
          <ul className="formula-editor-errors" role="alert">
            {report.errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}

        {report && report.valid ? (
          <p className="formula-editor-ok">
            Expression is valid.
            {report.unused.length > 0
              ? ` Unused parameter(s): ${report.unused.join(", ")}.`
              : ""}
          </p>
        ) : null}

        <div className="formula-editor-params">
          <div className="formula-editor-params-head">
            <h4>Parameters</h4>
            <button
              type="button"
              className="alerts-mini-btn"
              onClick={addParameter}
            >
              Add parameter
            </button>
          </div>

          {draft.parameters.length === 0 ? (
            <p className="alerts-empty">
              No parameters yet. Every name used in the expression needs one.
            </p>
          ) : (
            draft.parameters.map((parameter, index) => (
              <div className="formula-param-row" key={index}>
                <input
                  aria-label={`Parameter ${index + 1} name`}
                  placeholder="on_hand"
                  value={parameter.key}
                  onChange={(event) =>
                    changeParameter(index, "key", event.target.value)
                  }
                />
                <input
                  aria-label={`Parameter ${index + 1} label`}
                  placeholder="On-hand units"
                  value={parameter.label}
                  onChange={(event) =>
                    changeParameter(index, "label", event.target.value)
                  }
                />
                <select
                  aria-label={`Parameter ${index + 1} type`}
                  value={parameter.type}
                  onChange={(event) =>
                    changeParameter(index, "type", event.target.value)
                  }
                >
                  <option value="number">number</option>
                  <option value="text">text</option>
                  <option value="boolean">boolean</option>
                </select>
                <input
                  aria-label={`Parameter ${index + 1} default`}
                  placeholder="default"
                  value={parameter.default ?? ""}
                  onChange={(event) =>
                    changeParameter(index, "default", event.target.value)
                  }
                />
                <button
                  type="button"
                  className="alerts-mini-btn"
                  aria-label={`Remove parameter ${index + 1}`}
                  onClick={() => removeParameter(index)}
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>

        {error ? (
          <p className="alerts-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="formula-editor-actions">
          <button type="button" className="alerts-btn" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="submit"
            className="alerts-btn primary"
            disabled={blocked}
          >
            {saving ? "Saving…" : "Save formula"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
