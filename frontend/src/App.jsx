import {
  useEffect,
  useRef,
  useState
} from "react";

import {
  fetchConversations,
  streamChat
} from "./api/chatStream.js";

import ChatMessage from "./components/ChatMessage.jsx";
import Workboard from "./components/Workboard.jsx";
import { AGENTS } from "./agents/registry.js";


function createInitialChat() {
  return {
    title: "",
    messages: [],
    conversationId: null,
    busy: false,
    suggestions: []
  };
}


function createInitialChats() {
  return Object.fromEntries(
    Object.keys(AGENTS).map(
      (agentId) => [
        agentId,
        createInitialChat()
      ]
    )
  );
}


export default function App() {
  const [
    activeAgent,
    setActiveAgent
  ] = useState("finance.finance");

  const [
    chats,
    setChats
  ] = useState(
    createInitialChats
  );

  const [
    input,
    setInput
  ] = useState("");

  const [
    conversationList,
    setConversationList
  ] = useState([]);

  const [
    clearOpen,
    setClearOpen
  ] = useState(false);

  const abortControllers =
    useRef({});

  const transcriptRef =
    useRef(null);

  const currentAgent =
    AGENTS[activeAgent];

  const currentChat =
    chats[activeAgent];

  const visibleSuggestions =
    currentChat.messages.length > 0
      ? currentChat.suggestions
      : currentAgent.starterPrompts;

  const canSend =
    Boolean(input.trim()) &&
    !currentChat.busy;


  useEffect(() => {
    async function loadConversations() {
      try {
        const result =
          await fetchConversations();

        setConversationList(
          Array.isArray(
            result.items
          )
            ? result.items
            : []
        );
      } catch (error) {
        console.error(
          "Unable to load conversations:",
          error
        );
      }
    }

    loadConversations();
  }, []);


  useEffect(() => {
    const element =
      transcriptRef.current;

    if (!element) {
      return;
    }

    requestAnimationFrame(() => {
      element.scrollTop =
        element.scrollHeight;
    });
  }, [
    activeAgent,
    currentChat.messages,
    currentChat.suggestions
  ]);


  useEffect(() => {
    return () => {
      Object.values(
        abortControllers.current
      ).forEach(
        (controller) =>
          controller.abort()
      );
    };
  }, []);


  function updateChat(
    agentId,
    updater
  ) {
    setChats(
      (currentChats) => {
        const current =
          currentChats[agentId];

        const updated =
          typeof updater ===
          "function"
            ? updater(current)
            : {
                ...current,
                ...updater
              };

        return {
          ...currentChats,
          [agentId]: updated
        };
      }
    );
  }


  function selectAgent(
    agentId
  ) {
    setActiveAgent(agentId);
    setClearOpen(false);
    setInput("");
  }


  function removeLoading(
    agentId
  ) {
    updateChat(
      agentId,
      (chat) => ({
        ...chat,

        messages:
          chat.messages.filter(
            (message) =>
              message.role !==
              "loading"
          )
      })
    );
  }


  function showLoading(
    agentId,
    text
  ) {
    updateChat(
      agentId,
      (chat) => ({
        ...chat,

        messages: [
          ...chat.messages.filter(
            (message) =>
              message.role !==
              "loading"
          ),

          {
            id:
              `loading-${agentId}`,

            role: "loading",
            text
          }
        ]
      })
    );
  }


  function handleStreamEvent(
    agentId,
    event
  ) {
    const data =
      event.data || {};

    if (
      data.conversation_id
    ) {
      updateChat(
        agentId,
        (chat) => ({
          ...chat,

          conversationId:
            data.conversation_id
        })
      );
    }

    switch (event.name) {
      case "status":
        showLoading(
          agentId,

          data.message ||
            "Running analysis"
        );

        break;


      case "tool_call":
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            messages: [
              ...chat.messages.filter(
                (message) =>
                  message.role !==
                  "loading"
              ),

              {
                id:
                  data.id ||
                  makeId(),

                role: "tool",

                tool:
                  data.tool,

                arguments:
                  data.arguments ||
                  {},

                result: null
              }
            ]
          })
        );

        showLoading(
          agentId,

          `Running ${formatToolName(
            data.tool
          )}`
        );

        break;


      case "tool_result":
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            messages:
              chat.messages.map(
                (message) => {
                  const matches =
                    message.role ===
                      "tool" &&
                    message.tool ===
                      data.tool &&
                    message.result ==
                      null;

                  if (!matches) {
                    return message;
                  }

                  return {
                    ...message,

                    result:
                      data.result
                  };
                }
              )
          })
        );

        showLoading(
          agentId,
          "Combining tool results"
        );

        break;


      case "assistant_response":
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            messages: [
              ...chat.messages.filter(
                (message) =>
                  message.role !==
                  "loading"
              ),

              {
                id:
                  data.id ||
                  makeId(),

                role:
                  "assistant",

                text:
                  data.text ||
                  "",

                blocks:
                  Array.isArray(
                    data.blocks
                  )
                    ? data.blocks
                    : [],

                time:
                  formatTime()
              }
            ]
          })
        );

        break;


      case "suggestions":
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            suggestions:
              Array.isArray(
                data.suggestions
              )
                ? data.suggestions
                : []
          })
        );

        break;


      case "done":
        removeLoading(
          agentId
        );

        break;


      case "error":
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            suggestions: [],

            messages: [
              ...chat.messages.filter(
                (message) =>
                  message.role !==
                  "loading"
              ),

              {
                id: makeId(),

                role: "error",

                text:
                  data.message ||
                  "The stream reported an error.",

                time:
                  formatTime()
              }
            ]
          })
        );

        break;


      default:
        console.debug(
          "Unhandled SSE event:",
          event
        );
    }
  }


  async function sendMessage(
    event
  ) {
    event.preventDefault();

    const text =
      input.trim();

    if (
      !text ||
      currentChat.busy
    ) {
      return;
    }

    const agentId =
      activeAgent;

    const conversationId =
      currentChat.conversationId;

    const controller =
      new AbortController();

    abortControllers.current[
      agentId
    ] = controller;

    setInput("");

    updateChat(
      agentId,
      (chat) => ({
        ...chat,

        title:
          chat.title ||
          generateTitle(text),

        busy: true,

        suggestions: [],

        messages: [
          ...chat.messages,

          {
            id: makeId(),

            role: "user",

            text,

            time:
              formatTime()
          }
        ]
      })
    );

    try {
      await streamChat({
        agent: agentId,
        message: text,
        conversationId,

        signal:
          controller.signal,

        onEvent:
          (streamEvent) =>
            handleStreamEvent(
              agentId,
              streamEvent
            )
      });
    } catch (error) {
      if (
        error.name !==
        "AbortError"
      ) {
        updateChat(
          agentId,
          (chat) => ({
            ...chat,

            suggestions: [],

            messages: [
              ...chat.messages.filter(
                (message) =>
                  message.role !==
                  "loading"
              ),

              {
                id: makeId(),

                role: "error",

                text:
                  `The service could not respond. ${error.message}`,

                time:
                  formatTime()
              }
            ]
          })
        );
      }
    } finally {
      delete abortControllers
        .current[agentId];

      updateChat(
        agentId,
        (chat) => ({
          ...chat,

          busy: false,

          messages:
            chat.messages.filter(
              (message) =>
                message.role !==
                "loading"
            )
        })
      );
    }
  }


  function clearCurrentChat() {
    const controller =
      abortControllers.current[
        activeAgent
      ];

    if (controller) {
      controller.abort();

      delete abortControllers
        .current[
          activeAgent
        ];
    }

    updateChat(
      activeAgent,
      createInitialChat()
    );

    setClearOpen(false);
    setInput("");
  }


  return (
    <main className="app-shell">
      <aside
        className="sidebar"
        aria-label="Agent chats"
      >
        <div className="brand">
          <div className="brand-mark">
            L
          </div>

          <div className="brand-copy">
            <strong>
              Ledgerline
            </strong>

            <span>
              Finance forum
            </span>
          </div>
        </div>


        <p className="section-label">
          Agent chats
        </p>


        <nav
          className="agent-list"
          aria-label="Choose an agent"
        >
          {Object.entries(
            AGENTS
          ).map(
            ([
              agentId,
              agent
            ]) => {
              const chat =
                chats[agentId];

              return (
                <button
                  key={agentId}
                  type="button"

                  className={
                    agentId ===
                    activeAgent
                      ? "agent-button active"
                      : "agent-button"
                  }

                  data-busy={
                    chat.busy
                  }

                  onClick={() =>
                    selectAgent(
                      agentId
                    )
                  }
                >
                  <span className="agent-avatar">
                    {agent.name.charAt(
                      0
                    )}
                  </span>

                  <span className="agent-copy">
                    <strong>
                      {agent.name}
                    </strong>

                    <small>
                      {chat.title ||
                        "New conversation"}
                    </small>
                  </span>

                  <span
                    className="activity-dot"
                    aria-hidden="true"
                  />
                </button>
              );
            }
          )}
        </nav>


        <footer className="sidebar-footer">
          {conversationList.length}
          {" "}
          saved conversation(s)
        </footer>
      </aside>


      <Workboard
        agentId={activeAgent}
        agentName={currentAgent.name}
      />


      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <span className="header-kicker">
              {currentAgent.name}
              {" "}
              chat

              {currentChat.busy
                ? " · working"
                : ""}
            </span>

            <h1>
              {currentChat.title ||
                `Ask ${currentAgent.name}`}
            </h1>
          </div>


          <div className="clear-area">
            <button
              type="button"
              className="clear-button"

              disabled={
                !currentChat
                  .messages.length
              }

              onClick={() =>
                setClearOpen(
                  (open) => !open
                )
              }
            >
              Clear chat
            </button>


            {clearOpen && (
              <div className="clear-confirm">
                <p>
                  Clear this agent&apos;s
                  local messages?
                </p>

                <div>
                  <button
                    type="button"

                    onClick={() =>
                      setClearOpen(
                        false
                      )
                    }
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    className="danger"

                    onClick={
                      clearCurrentChat
                    }
                  >
                    Clear
                  </button>
                </div>
              </div>
            )}
          </div>
        </header>


        <div
          ref={transcriptRef}
          className="transcript"
          aria-live="polite"
        >
          {!currentChat
            .messages.length ? (
            <EmptyState
              agent={
                currentAgent
              }
            />
          ) : (
            <ol className="message-list">
              {currentChat.messages.map(
                (message) => (
                  <ChatMessage
                    key={
                      message.id
                    }

                    message={
                      message
                    }

                    agentName={
                      currentAgent.name
                    }
                  />
                )
              )}
            </ol>
          )}
        </div>


        <footer className="composer-wrap">
          {visibleSuggestions?.length >
            0 && (
            <section
              className="prompt-suggestions"
              aria-label="Suggested prompts"
            >
              <div className="prompt-suggestions-heading">
                <span className="prompt-suggestions-spark">

                </span>

                <span>
                  {currentChat.messages.length > 0
                  ? "Continue exploring"
                  : "Try asking"}
                </span>
              </div>

              <div className="prompt-suggestions-list">
                {visibleSuggestions.map(
                  (
                    suggestion
                  ) => (
                    <button
                  key={suggestion}
                  type="button"
                  className="prompt-suggestion-button"
                  disabled={currentChat.busy}
                  onClick={() => {
                    setInput(suggestion);
                  }}
                >
                  <span className="prompt-suggestion-text">
                    {suggestion}
                  </span>

                  <span
                    className="prompt-suggestion-arrow"
                    aria-hidden="true"
                  >
                    ↗
                  </span>
                </button>
                  )
                )}
              </div>
            </section>
          )}


          <form
            className="composer"
            onSubmit={
              sendMessage
            }
          >
            <textarea
              value={input}

              disabled={
                currentChat.busy
              }

              rows={1}
              maxLength={2000}

              placeholder={
                currentAgent.prompt
              }

              aria-label={
                `Message ${currentAgent.name}`
              }

              onChange={
                (event) =>
                  setInput(
                    event.target
                      .value
                  )
              }

              onKeyDown={
                (event) => {
                  if (
                    event.key ===
                      "Enter" &&
                    !event.shiftKey
                  ) {
                    event.preventDefault();

                    event.currentTarget
                      .form
                      .requestSubmit();
                  }
                }
              }
            />

            <button
              type="submit"
              className="send-button"
              disabled={!canSend}
            >
              Send
            </button>
          </form>


          <p className="composer-note">
            AI responses should be
            reviewed before financial
            decisions are made.
          </p>
        </footer>
      </section>
    </main>
  );
}


function EmptyState({
  agent
}) {
  return (
    <div className="empty-state">
      <div className="empty-content">
        <div className="empty-icon">
          {agent.name.charAt(
            0
          )}
        </div>

        <h2>
          {agent.name}, ready
          when you are
        </h2>

        <p>
          {agent.description}
        </p>
      </div>
    </div>
  );
}


function makeId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}


function formatTime() {
  return new Intl.DateTimeFormat(
    undefined,
    {
      hour: "numeric",
      minute: "2-digit"
    }
  ).format(new Date());
}


function generateTitle(
  message
) {
  const normalized =
    message
      .replace(/\s+/g, " ")
      .trim();

  if (
    normalized.length <= 42
  ) {
    return normalized;
  }

  const clipped =
    normalized.slice(0, 42);

  const lastSpace =
    clipped.lastIndexOf(" ");

  const cutoff =
    lastSpace > 24
      ? lastSpace
      : 42;

  return `${clipped.slice(
    0,
    cutoff
  )}...`;
}


function formatToolName(
  tool
) {
  return String(
    tool || "tool"
  ).replaceAll("_", " ");
}