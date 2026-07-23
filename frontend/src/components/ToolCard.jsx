export default function ToolCard({
  message
}) {
  const completed =
    message.result !== null &&
    message.result !== undefined;

  return (
    <li className="tool-message">
      <details className="tool-card">
        <summary>
          <span
            className="tool-icon"
            aria-hidden="true"
          >
            ⚙
          </span>

          <span className="tool-name">
            Tool call{" "}
            {formatToolName(
              message.tool
            )}
          </span>

          <span
            className={
              completed
                ? "tool-status completed"
                : "tool-status running"
            }
          >
            {completed
              ? "Completed"
              : "Running"}
          </span>
        </summary>

        <div className="tool-content">
          <ToolSection
            label="Arguments"
            value={message.arguments}
            emptyText="No arguments"
          />

          <ToolSection
            label="Result"
            value={message.result}
            emptyText="Waiting for result..."
          />
        </div>
      </details>
    </li>
  );
}

function ToolSection({
  label,
  value,
  emptyText
}) {
  return (
    <section className="tool-section">
      <strong>{label}</strong>

      <pre>
        {value !== null &&
        value !== undefined
          ? JSON.stringify(
              value,
              null,
              2
            )
          : emptyText}
      </pre>
    </section>
  );
}

function formatToolName(tool) {
  return String(
    tool || "unknown tool"
  ).replaceAll("_", " ");
}