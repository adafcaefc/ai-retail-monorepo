export default function KpiInsightPreview({
  kpi,
  view,
  agentName,
  busy = false,
  onClose,
  onContinue
}) {
  if (!kpi) {
    return null;
  }

  const status = normaliseStatus(
    kpi.status || (kpi.alert ? "bad" : "good")
  );

  const progress =
    typeof kpi.progress === "number"
      ? Math.round(kpi.progress * 100)
      : null;

  const value = [kpi.value, kpi.unit]
    .filter(Boolean)
    .join(" ");

  const viewTitle =
    view?.title || "the related dashboard view";

  const summary = buildPreviewSummary({
    kpi,
    status,
    progress,
    value,
    viewTitle
  });

  return (
    <section
      className={`kpi-insight-preview status-${status}`}
      aria-labelledby="kpi-insight-preview-title"
      aria-live="polite"
    >
      <span
        className="kpi-insight-pointer"
        aria-hidden="true"
      />

      <div className="kpi-insight-head">
        <div className="kpi-insight-heading">
          <span
            className="kpi-insight-icon"
            aria-hidden="true"
          >
            <SparkIcon />
          </span>

          <div>
            <span className="kpi-insight-eyebrow">
              KPI quick insight
            </span>

            <h2 id="kpi-insight-preview-title">
              {kpi.label}
            </h2>
          </div>
        </div>

        <button
          type="button"
          className="kpi-insight-close"
          aria-label="Close KPI quick insight"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="kpi-insight-metrics">
        <span
          className={`kpi-insight-status status-${status}`}
        >
          <span
            className="kpi-insight-status-dot"
            aria-hidden="true"
          />

          {statusLabel(status)}
        </span>

        <strong className="kpi-insight-value">
          {value || "Value unavailable"}
        </strong>

        {kpi.delta ? (
          <span className="kpi-insight-delta">
            {kpi.delta}
          </span>
        ) : null}

        {progress !== null ? (
          <span className="kpi-insight-progress-label">
            {progress}% toward target
          </span>
        ) : null}
      </div>

      {progress !== null ? (
        <div
          className="kpi-insight-progress"
          role="progressbar"
          aria-label={`${kpi.label} progress toward target`}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={Math.min(100, progress)}
        >
          <span
            className="kpi-insight-progress-fill"
            style={{
              width: `${Math.min(100, Math.max(0, progress))}%`
            }}
          />
        </div>
      ) : null}

      <div className="kpi-insight-copy">
        <p>{summary}</p>

        <p className="kpi-insight-source-note">
          This snapshot uses the currently available dashboard
          payload only. Continue to {agentName} chat for deeper
          analysis of drivers, risks, and possible actions.
        </p>
      </div>

      <div className="kpi-insight-view">
        <span className="kpi-insight-view-label">
          Selected view
        </span>

        <strong>{viewTitle}</strong>

        {view?.note ? (
          <span>{view.note}</span>
        ) : null}
      </div>

      <div className="kpi-insight-actions">
        <button
          type="button"
          className="kpi-insight-secondary"
          onClick={onClose}
        >
          Close
        </button>

        <button
          type="button"
          className="kpi-insight-primary"
          disabled={busy}
          onClick={onContinue}
        >
          {busy
            ? `${agentName} chat is working`
            : `Continue in ${agentName} chat`}
          {!busy ? (
            <span aria-hidden="true">→</span>
          ) : null}
        </button>
      </div>
    </section>
  );
}

function buildPreviewSummary({
  kpi,
  status,
  progress,
  value,
  viewTitle
}) {
  const subject = kpi.label || "This KPI";
  const displayValue = value || "its current value";

  let statusSentence;

  if (status === "bad") {
    statusSentence =
      `${subject} is currently flagged for attention at ` +
      `${displayValue}.`;
  } else if (status === "warn") {
    statusSentence =
      `${subject} is currently within the caution range at ` +
      `${displayValue}.`;
  } else {
    statusSentence =
      `${subject} is currently shown within its expected status ` +
      `at ${displayValue}.`;
  }

  const progressSentence =
    progress !== null
      ? ` It is approximately ${progress}% toward the stated target.`
      : "";

  const trendSentence =
    Array.isArray(kpi.trend) && kpi.trend.length >= 2
      ? " A historical series is available for the mini trend shown on the KPI card."
      : "";

  const viewSentence =
    ` The selected “${viewTitle}” view provides the related ` +
    "dashboard breakdown.";

  return (
    statusSentence +
    progressSentence +
    trendSentence +
    viewSentence
  );
}

function normaliseStatus(status) {
  if (
    status === "good" ||
    status === "warn" ||
    status === "bad"
  ) {
    return status;
  }

  return "good";
}

function statusLabel(status) {
  if (status === "bad") {
    return "Needs attention";
  }

  if (status === "warn") {
    return "Caution";
  }

  return "On track";
}

function SparkIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 2.5l1.9 4.9 4.9 1.9-4.9 1.9L12 16l-1.9-4.8L5.2 9.3l4.9-1.9L12 2.5zm6.5 10l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9.9-2.3z"
      />
    </svg>
  );
}