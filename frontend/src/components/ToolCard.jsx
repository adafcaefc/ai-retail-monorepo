import { useState } from "react";

/**
 * A single agent tool step, rendered as a compact, human-readable card
 * instead of a raw JSON dump. Collapsed by default; expandable for the
 * arguments and full result when a user wants the detail.
 */
export default function ToolCard({ message }) {
  const [open, setOpen] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);

  const completed =
    message.result !== null && message.result !== undefined;

  const meta = describeTool(message.tool);
  const args = normalizeObject(message.arguments);
  const argEntries = Object.entries(args);
  const resultSummary = summarizeResult(message.result);

  return (
    <li className="tool-message">
      <div className={"tool-step" + (completed ? " done" : " running")}>
        <button
          type="button"
          className="tool-step-head"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <span className="tool-step-icon" aria-hidden="true">
            {meta.icon}
          </span>

          <span className="tool-step-copy">
            <span className="tool-step-title">
              {completed ? meta.pastLabel : meta.label}
            </span>
            <span className="tool-step-sub">{meta.name}</span>
          </span>

          <span
            className={
              "tool-step-status" + (completed ? " done" : " running")
            }
          >
            {completed ? (
              <>
                <span className="tool-step-check" aria-hidden="true">
                  ✓
                </span>
                Done
              </>
            ) : (
              <>
                <span
                  className="tool-step-spinner"
                  aria-hidden="true"
                />
                Working
              </>
            )}
          </span>

          <span className="tool-step-chevron" aria-hidden="true">
            {open ? "▴" : "▾"}
          </span>
        </button>

        {open ? (
          <div className="tool-step-detail">
            {argEntries.length > 0 ? (
              <div className="tool-step-block">
                <span className="tool-step-block-label">Inputs</span>
                <div className="tool-arg-pills">
                  {argEntries.map(([key, value]) => (
                    <span key={key} className="tool-arg-pill">
                      <span className="tool-arg-key">
                        {humanizeKey(key)}
                      </span>
                      <span className="tool-arg-value">
                        {formatScalar(value)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="tool-step-block">
              <span className="tool-step-block-label">Result</span>
              {completed ? (
                <div className="tool-result">
                  <p className="tool-result-summary">{resultSummary}</p>

                  <button
                    type="button"
                    className="tool-raw-toggle"
                    onClick={() => setRawOpen((value) => !value)}
                  >
                    {rawOpen ? "Hide raw data" : "View raw data"}
                  </button>

                  {rawOpen ? (
                    <pre className="tool-raw">
                      {safeStringify(message.result)}
                    </pre>
                  ) : null}
                </div>
              ) : (
                <p className="tool-result-waiting">
                  Waiting for the result…
                </p>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** Friendly verb + icon per tool, with a humanized fallback. */
function describeTool(tool) {
  const name = formatToolName(tool);
  const key = String(tool || "").toLowerCase();

  const rules = [
    { match: ["query", "sql", "freeform"], icon: "🔎", label: "Querying the data", pastLabel: "Queried the data" },
    { match: ["finance", "kpi", "performance", "margin", "ebitda"], icon: "📊", label: "Analyzing performance", pastLabel: "Analyzed performance" },
    { match: ["collection", "receivable", "dso", "aging"], icon: "📥", label: "Reviewing collections", pastLabel: "Reviewed collections" },
    { match: ["cashflow", "liquidity", "treasury"], icon: "💧", label: "Checking liquidity", pastLabel: "Checked liquidity" },
    { match: ["leakage", "duplicate", "anomaly", "fraud"], icon: "🛡️", label: "Scanning for leakage", pastLabel: "Scanned for leakage" },
    { match: ["simulate", "scenario", "whatif", "recalculate"], icon: "🧮", label: "Running a scenario", pastLabel: "Ran a scenario" },
    { match: ["alert", "monitor"], icon: "🔔", label: "Checking alerts", pastLabel: "Checked alerts" }
  ];

  for (const rule of rules) {
    if (rule.match.some((token) => key.includes(token))) {
      return { ...rule, name };
    }
  }

  return {
    icon: "⚙️",
    label: "Running a tool",
    pastLabel: "Ran a tool",
    name
  };
}

function summarizeResult(result) {
  if (result === null || result === undefined) {
    return "No result returned.";
  }

  if (Array.isArray(result)) {
    return `Returned ${result.length} row${
      result.length === 1 ? "" : "s"
    }.`;
  }

  if (typeof result === "object") {
    const keys = Object.keys(result);

    if (keys.length === 0) {
      return "Returned an empty result.";
    }

    if (Array.isArray(result.rows)) {
      return `Returned ${result.rows.length} row${
        result.rows.length === 1 ? "" : "s"
      }.`;
    }

    const preview = keys
      .slice(0, 3)
      .map((key) => humanizeKey(key))
      .join(", ");

    return `Returned ${keys.length} field${
      keys.length === 1 ? "" : "s"
    }: ${preview}${keys.length > 3 ? "…" : ""}.`;
  }

  return String(result);
}

function normalizeObject(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value;
  }
  return {};
}

function formatScalar(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "object") {
    return Array.isArray(value)
      ? `${value.length} items`
      : `${Object.keys(value).length} fields`;
  }
  const text = String(value);
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

function humanizeKey(key) {
  return String(key)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function safeStringify(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatToolName(tool) {
  return String(tool || "unknown tool").replaceAll("_", " ");
}
