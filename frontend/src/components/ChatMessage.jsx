import BlockRenderer from "./BlockRenderer.jsx";
import ToolCard from "./ToolCard.jsx";

export default function ChatMessage({
  message,
  agentName
}) {
  if (
    message.role === "tool"
  ) {
    return (
      <ToolCard
        message={message}
      />
    );
  }

  if (
    message.role === "loading"
  ) {
    return (
      <li className="loading-row">
        <span
          className="spinner"
          aria-hidden="true"
        />

        <span>
          {message.text}
        </span>
      </li>
    );
  }

  const isUser =
    message.role === "user";

  return (
    <li
      className={
        `message ${message.role}`
      }
    >
      {!isUser && (
        <span
          className="message-avatar"
          aria-hidden="true"
        >
          {message.role === "error"
            ? "!"
            : "AI"}
        </span>
      )}

      <div className="message-body">
        {message.text && (
          <div className="bubble">
            {message.text}
          </div>
        )}

        {Array.isArray(
          message.blocks
        ) &&
          message.blocks.length >
            0 && (
            <div className="block-stack">
              {message.blocks.map(
                (block, index) => (
                  <BlockRenderer
                    key={
                      block.id ||
                      `${block.type}-${index}`
                    }
                    block={block}
                  />
                )
              )}
            </div>
          )}

        <div className="message-meta">
          {isUser
            ? "You"
            : agentName}

          {message.time
            ? ` · ${message.time}`
            : ""}
        </div>
      </div>
    </li>
  );
}