import { useEffect, useRef } from "react";

import { useLanguage } from "../LanguageProvider.jsx";

/**
 * The right-hand drill-down panel a KPI tile opens.
 *
 * A drawer rather than `Modal.jsx`, which is centred and sized for a form.
 * This one is a reading surface pinned beside the board: the tile that opened
 * it stays visible on the left, so the reader can see the number and its
 * decomposition at once. Losing that was the reason not to reuse the dialog.
 *
 * Deliberately dumb. It owns the shell — backdrop, escape, focus, scroll
 * reset — and nothing about what a metric means. Each board passes its own
 * sections, because "this metric by category" is a different computation on
 * every board and the one thing that must not live here is a second opinion
 * about how a KPI is built.
 */
export default function DrillDrawer({ title, subtitle, onClose, children }) {
  const { t } = useLanguage();
  const panelRef = useRef(null);
  const closeRef = useRef(null);

  // Escape closes, and focus starts inside the panel so a keyboard user is not
  // left behind on the tile with the drawer open in front of them.
  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    closeRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // A new metric reuses the same panel, so reset the scroll — otherwise the
  // second tile opens halfway down, past its own headline figure.
  // Feature-detected because jsdom implements no scrolling at all, and a
  // missing method there is not a reason for the drawer to fail to mount.
  useEffect(() => {
    panelRef.current?.scrollTo?.({ top: 0 });
  }, [title]);

  return (
    <div className="drill-backdrop" role="presentation" onClick={onClose}>
      <aside
        ref={panelRef}
        className="drill-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drill-head">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            className="drill-close"
            aria-label={t("Close")}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="drill-body">{children}</div>
      </aside>
    </div>
  );
}

/** One titled block inside the drawer. */
export function DrillSection({ icon, title, note, children }) {
  const { t } = useLanguage();
  return (
    <section className="drill-section">
      <h3>
        <span aria-hidden="true">{icon}</span> {t(title)}
      </h3>
      {note ? <p className="drill-section-note">{note}</p> : null}
      {children}
    </section>
  );
}

/**
 * A ranked horizontal bar list — the drawer's only chart shape.
 *
 * Bars are drawn against the largest value in the list rather than the metric
 * total, so a long tail stays readable. Rows carry the raw figure beside them
 * because the bar answers "which is biggest" and only the number answers
 * "by how much".
 */
export function DrillBars({ rows, format, emptyLabel = "Nothing in scope." }) {
  const { t } = useLanguage();
  if (!rows?.length) return <p className="drill-empty">{t(emptyLabel)}</p>;

  const peak = Math.max(...rows.map((row) => Math.abs(row.value)), 0) || 1;

  return (
    <ul className="drill-bars">
      {rows.map((row) => (
        <li key={row.id ?? row.label}>
          <span className="drill-bar-label" title={row.label}>
            {row.label}
          </span>
          <span className="drill-bar-track">
            <span
              className="drill-bar-fill"
              style={{ width: `${(Math.abs(row.value) / peak) * 100}%` }}
            />
          </span>
          <span className="drill-bar-value">{format(row.value)}</span>
        </li>
      ))}
    </ul>
  );
}
