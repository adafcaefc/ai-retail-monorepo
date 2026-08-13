import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createFormula,
  deleteFormula,
  fetchFormulas,
  updateFormula
} from "../../../api/formulas.js";
import { ListSkeleton } from "../../../components/Skeleton.jsx";
import FormulaCard from "./FormulaCard.jsx";
import FormulaEditor from "./FormulaEditor.jsx";

/**
 * The retail formula library: browse, verify against the workbook's worked
 * examples, and edit.
 *
 * Unlike the other static pages this one does call the backend
 * (`/api/formulas`). `isPage`/`dashboardOnly` only suppress the *agent* APIs;
 * a page is still free to own an endpoint.
 */
export default function FormulaManager() {
  const [formulas, setFormulas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState("");

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
    }
    setError("");
    try {
      const payload = await fetchFormulas();
      setFormulas(Array.isArray(payload.items) ? payload.items : []);
    } catch (loadError) {
      setFormulas([]);
      setError(loadError.message || "Unable to load formulas.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return formulas;
    }
    return formulas.filter((formula) =>
      [
        formula.name,
        formula.logic,
        formula.expression,
        formula.grain,
        formula.sheet
      ]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(needle))
    );
  }, [formulas, query]);

  const save = useCallback(
    async (draft) => {
      setSaving(true);
      try {
        if (editing?.formula) {
          await updateFormula(editing.formula.id, draft);
        } else {
          await createFormula(draft);
        }
        setEditing(null);
        await load({ silent: true });
      } finally {
        setSaving(false);
      }
    },
    [editing, load]
  );

  const remove = useCallback(
    async (formula) => {
      setDeletingId(formula.id);
      setError("");
      try {
        await deleteFormula(formula.id);
        await load({ silent: true });
      } catch (deleteError) {
        setError(deleteError.message || "Could not delete this formula.");
      } finally {
        setDeletingId("");
      }
    },
    [load]
  );

  return (
    <section
      className="static-page"
      data-testid="formula-manager"
      aria-label="Formula Manager"
    >
      <h2>Formula Manager</h2>
      <p className="formula-page-intro">
        The retail calculation library. Each formula carries its tweakable
        parameters and the workbook examples it was verified against.
      </p>

      <div className="formula-toolbar">
        <input
          type="search"
          className="formula-search"
          placeholder="Search formulas…"
          aria-label="Search formulas"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="formula-count">
          {visible.length} of {formulas.length}
        </span>
        <button
          type="button"
          className="alerts-btn primary"
          onClick={() => setEditing({ formula: null })}
        >
          New formula
        </button>
      </div>

      {error ? (
        <p className="alerts-error" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <ListSkeleton rows={5} label="Loading formulas" />
      ) : visible.length === 0 ? (
        <p className="alerts-empty">
          {formulas.length === 0
            ? "No formulas stored yet."
            : "No formulas match that search."}
        </p>
      ) : (
        <div className="formula-list">
          {visible.map((formula) => (
            <FormulaCard
              key={formula.id}
              formula={formula}
              onEdit={(target) => setEditing({ formula: target })}
              onDelete={remove}
              deleting={deletingId === formula.id}
            />
          ))}
        </div>
      )}

      {editing ? (
        <FormulaEditor
          formula={editing.formula}
          saving={saving}
          onCancel={() => setEditing(null)}
          onSave={save}
        />
      ) : null}
    </section>
  );
}
