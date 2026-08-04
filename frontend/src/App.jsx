import { useEffect, useRef, useState } from "react";

import { streamChat } from "./api/chatStream.js";

import ChatMessage from "./components/ChatMessage.jsx";
import Workboard from "./components/Workboard.jsx";
import ProblemToasts from "./components/ProblemToasts.jsx";
import AppTopbar from "./components/AppTopbar.jsx";
import AlertsPanel from "./components/AlertsPanel.jsx";
import UserIcon from "./assets/user-icon.svg";
import {
  AgentListSkeleton,
  DashboardSkeleton,
} from "./components/Skeleton.jsx";
import { buildInfoPrompt } from "./infoRegistry.js";
import { useAgents } from "./agents/AgentsProvider.jsx";
import { useLanguage } from "./LanguageProvider.jsx";

const CHAT_WIDTH_KEY = "ledgerline.chatWidth";
const CHAT_WIDTH_MIN = 320;
const CHAT_WIDTH_MAX = 760;
const CHAT_WIDTH_DEFAULT = 380;
const SHELL_EDGE_PADDING = 14;

const SIDEBAR_KEY = "ledgerline.sidebarOpen";

// How long a freshly expanded folder shows placeholder rows. Long enough to
// read as "the list is coming", short enough not to feel like a stall.
const FOLDER_REVEAL_MS = 420;

function readStoredSidebarOpen() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.localStorage.getItem(SIDEBAR_KEY) !== "closed";
}

function clampChatWidth(value) {
  if (!Number.isFinite(value)) {
    return CHAT_WIDTH_DEFAULT;
  }
  return Math.min(CHAT_WIDTH_MAX, Math.max(CHAT_WIDTH_MIN, Math.round(value)));
}

function readStoredChatWidth() {
  if (typeof window === "undefined") {
    return CHAT_WIDTH_DEFAULT;
  }
  const stored = Number(window.localStorage.getItem(CHAT_WIDTH_KEY));
  return stored ? clampChatWidth(stored) : CHAT_WIDTH_DEFAULT;
}

function createInitialChat() {
  return {
    title: "",
    messages: [],
    conversationId: null,
    busy: false,
    suggestions: [],
    draft: "",
  };
}

// Stand-in while the module list is still loading, so hooks below can read
// `currentChat` unconditionally. Its identity is stable on purpose.
const EMPTY_CHAT = createInitialChat();

export default function App() {
  const {
    agents,
    agentIds,
    groups,
    loading: agentsLoading,
    error: agentsError,
  } = useAgents();

  // The starter prompts are the first words a CFO reads in the chat panel, so
  // they have to follow the language toggle like the board does (QC-042 with
  // QC-058). Model-written follow-ups pass through untouched: translate()
  // returns anything it has no entry for unchanged.
  const { t } = useLanguage();

  const [activeAgent, setActiveAgent] = useState(null);

  // The board's server_filters selections (Legal entity, Period, Category
  // group — whichever ones the active agent offers). Lives here, not inside
  // Workboard, because chat also needs the same values: a question asked
  // while the board is scoped should be answered about that same slice, not
  // the whole ledger (see streamChat's legalEntityId/period/categoryGroup
  // and scope.py server-side). Not reset on an agent switch — see the note
  // beside Workboard's own copy of this reasoning. A flat object keyed by
  // `server_filters[].id` rather than one state variable per filter, so a
  // fifth filter someday needs no new `useState` here.
  const [serverFilters, setServerFilters] = useState({
    legal_entity_id: "ALL",
    period: "ALL",
    category_group: "ALL",
  });

  function setServerFilter(id, value) {
    setServerFilters((current) => ({ ...current, [id]: value }));
  }

  const [chats, setChats] = useState({});

  const [collapsedFolders, setCollapsedFolders] = useState(() => new Set());

  // Folders that just expanded and are still showing placeholder rows.
  const [revealingFolders, setRevealingFolders] = useState(() => new Set());

  const [sidebarOpen, setSidebarOpen] = useState(readStoredSidebarOpen);

  const [clearOpen, setClearOpen] = useState(false);

  const [isChatOpen, setIsChatOpen] = useState(false);

  const [chatWidth, setChatWidth] = useState(readStoredChatWidth);

  const [resizing, setResizing] = useState(false);

  const abortControllers = useRef({});

  const transcriptRef = useRef(null);

  const composerRef = useRef(null);

  const revealTimers = useRef(new Map());

  const currentAgent = agents[activeAgent] || null;

  const currentChat = chats[activeAgent] || EMPTY_CHAT;

  const input = currentChat.draft || "";

  const visibleSuggestions =
    currentChat.messages.length > 0
      ? currentChat.suggestions
      : (currentAgent?.starterPrompts ?? []);

  const canSend = Boolean(input.trim()) && !currentChat.busy;

  // Seed one chat per enabled module once the backend list arrives, keeping
  // any chat already in flight. The first module is the default board.
  useEffect(() => {
    if (agentIds.length === 0) {
      return;
    }

    setChats((current) => {
      const next = { ...current };
      let changed = false;

      for (const agentId of agentIds) {
        if (!next[agentId]) {
          next[agentId] = createInitialChat();
          changed = true;
        }
      }

      return changed ? next : current;
    });

    setActiveAgent((current) =>
      current && agentIds.includes(current) ? current : agentIds[0],
    );
  }, [agentIds]);

  useEffect(() => {
    const element = transcriptRef.current;

    if (!element) {
      return;
    }

    requestAnimationFrame(() => {
      element.scrollTop = element.scrollHeight;
    });
  }, [activeAgent, currentChat.messages, currentChat.suggestions]);

  useEffect(() => {
    if (!isChatOpen) {
      return;
    }

    function handleEscape(event) {
      if (event.key === "Escape" && !clearOpen) {
        setIsChatOpen(false);
      }
    }

    window.addEventListener("keydown", handleEscape);

    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isChatOpen, clearOpen]);

  // Grow the composer to fit its content (up to a max), so injected
  // suggestions and multi-line drafts are never clipped.
  useEffect(() => {
    const element = composerRef.current;

    if (!element) {
      return;
    }

    element.style.height = "auto";

    element.style.height = `${element.scrollHeight}px`;
  }, [input, activeAgent]);

  // Reveal a scroll surface's scrollbar only while it is actively scrolling,
  // then fade it back out after a short idle. Hover is handled in CSS.
  useEffect(() => {
    const elements = [transcriptRef.current, composerRef.current].filter(
      Boolean,
    );

    const timers = new Map();

    const handlers = elements.map((element) => {
      const onScroll = () => {
        element.classList.add("is-scrolling");

        window.clearTimeout(timers.get(element));

        timers.set(
          element,
          window.setTimeout(() => {
            element.classList.remove("is-scrolling");
          }, 900),
        );
      };

      element.addEventListener("scroll", onScroll, { passive: true });

      return { element, onScroll };
    });

    return () => {
      handlers.forEach(({ element, onScroll }) => {
        element.removeEventListener("scroll", onScroll);
      });

      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [activeAgent]);

  useEffect(() => {
    const timers = revealTimers.current;

    return () => {
      Object.values(abortControllers.current).forEach((controller) =>
        controller.abort(),
      );

      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  function startResize(startEvent) {
    startEvent.preventDefault();
    setResizing(true);

    const applyWidth = (clientX) => {
      const fromRight = window.innerWidth - clientX - SHELL_EDGE_PADDING;

      setChatWidth(clampChatWidth(fromRight));
    };

    const onMove = (moveEvent) => {
      applyWidth(moveEvent.clientX);
    };

    const onUp = () => {
      setResizing(false);

      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);

      setChatWidth((width) => {
        window.localStorage.setItem(CHAT_WIDTH_KEY, String(width));
        return width;
      });
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function handleResizeKey(event) {
    const step = event.shiftKey ? 48 : 16;

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setChatWidth((width) => {
        const next = clampChatWidth(width + step);
        window.localStorage.setItem(CHAT_WIDTH_KEY, String(next));
        return next;
      });
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setChatWidth((width) => {
        const next = clampChatWidth(width - step);
        window.localStorage.setItem(CHAT_WIDTH_KEY, String(next));
        return next;
      });
    }
  }

  function updateChat(agentId, updater) {
    setChats((currentChats) => {
      const current = currentChats[agentId];

      const updated =
        typeof updater === "function"
          ? updater(current)
          : {
              ...current,
              ...updater,
            };

      return {
        ...currentChats,
        [agentId]: updated,
      };
    });
  }

  function setCurrentDraft(value) {
    if (!activeAgent) {
      return;
    }

    updateChat(activeAgent, (chat) => ({
      ...chat,
      draft: value,
    }));
  }

  function selectAgent(agentId) {
    setActiveAgent(agentId);
    setClearOpen(false);
  }

  function toggleChat() {
    setClearOpen(false);

    setIsChatOpen((open) => !open);
  }

  function closeChat() {
    setClearOpen(false);
    setIsChatOpen(false);
  }

  function removeLoading(agentId) {
    updateChat(agentId, (chat) => ({
      ...chat,

      messages: chat.messages.filter((message) => message.role !== "loading"),
    }));
  }

  function showLoading(agentId, text) {
    updateChat(agentId, (chat) => ({
      ...chat,

      messages: [
        ...chat.messages.filter((message) => message.role !== "loading"),

        {
          id: `loading-${agentId}`,
          role: "loading",
          text,
        },
      ],
    }));
  }

  function handleStreamEvent(agentId, event) {
    const data = event.data || {};

    if (data.conversation_id) {
      updateChat(agentId, (chat) => ({
        ...chat,

        conversationId: data.conversation_id,
      }));
    }

    switch (event.name) {
      case "status":
        showLoading(
          agentId,

          data.message || "Running analysis",
        );

        break;

      case "tool_call":
        updateChat(agentId, (chat) => ({
          ...chat,

          messages: [
            ...chat.messages.filter((message) => message.role !== "loading"),

            {
              id: data.id || makeId(),

              role: "tool",

              tool: data.tool,

              arguments: data.arguments || {},

              result: null,
            },
          ],
        }));

        showLoading(
          agentId,

          `Running ${formatToolName(data.tool)}`,
        );

        break;

      case "tool_result":
        updateChat(agentId, (chat) => ({
          ...chat,

          messages: chat.messages.map((message) => {
            const matches =
              message.role === "tool" &&
              message.tool === data.tool &&
              message.result == null;

            if (!matches) {
              return message;
            }

            return {
              ...message,

              result: data.result,
            };
          }),
        }));

        showLoading(agentId, "Combining tool results");

        break;

      case "assistant_response":
        updateChat(agentId, (chat) => ({
          ...chat,

          messages: [
            ...chat.messages.filter((message) => message.role !== "loading"),

            {
              id: data.id || makeId(),

              role: "assistant",

              text: data.text || "",

              blocks: Array.isArray(data.blocks) ? data.blocks : [],

              time: formatTime(),
            },
          ],
        }));

        break;

      case "suggestions":
        updateChat(agentId, (chat) => ({
          ...chat,

          suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
        }));

        break;

      case "done":
        removeLoading(agentId);

        break;

      case "error":
        updateChat(agentId, (chat) => ({
          ...chat,

          suggestions: [],

          messages: [
            ...chat.messages.filter((message) => message.role !== "loading"),

            {
              id: makeId(),

              role: "error",

              text: data.message || "The stream reported an error.",

              time: formatTime(),
            },
          ],
        }));

        break;

      default:
        console.debug("Unhandled SSE event:", event);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();

    const text = input.trim();

    if (!text) {
      return;
    }

    setCurrentDraft("");

    await submitText(text);
  }

  async function submitText(rawText) {
    const text = String(rawText || "").trim();

    if (!text || currentChat.busy) {
      return;
    }

    const agentId = activeAgent;

    const conversationId = currentChat.conversationId;

    const controller = new AbortController();

    abortControllers.current[agentId] = controller;

    updateChat(agentId, (chat) => ({
      ...chat,

      title: chat.title || generateTitle(text),

      busy: true,

      suggestions: [],

      messages: [
        ...chat.messages,

        {
          id: makeId(),

          role: "user",

          text,

          time: formatTime(),
        },
      ],
    }));

    try {
      await streamChat({
        agent: agentId,
        message: text,
        conversationId,
        legalEntityId: serverFilters.legal_entity_id,
        period: serverFilters.period,
        categoryGroup: serverFilters.category_group,

        signal: controller.signal,

        onEvent: (streamEvent) => handleStreamEvent(agentId, streamEvent),
      });
    } catch (error) {
      if (error.name !== "AbortError") {
        updateChat(agentId, (chat) => ({
          ...chat,

          suggestions: [],

          messages: [
            ...chat.messages.filter((message) => message.role !== "loading"),

            {
              id: makeId(),

              role: "error",

              text: `The service could not respond. ${error.message}`,

              time: formatTime(),
            },
          ],
        }));
      }
    } finally {
      delete abortControllers.current[agentId];

      updateChat(agentId, (chat) => ({
        ...chat,

        busy: false,

        messages: chat.messages.filter((message) => message.role !== "loading"),
      }));
    }
  }

  function clearCurrentChat() {
    const controller = abortControllers.current[activeAgent];

    if (controller) {
      controller.abort();

      delete abortControllers.current[activeAgent];
    }

    updateChat(activeAgent, createInitialChat());

    setClearOpen(false);
  }

  function askKpiInsight(request) {
    if (currentChat.busy) {
      return;
    }

    setClearOpen(false);
    setIsChatOpen(true);

    submitText(
      request?.entry
        ? buildInfoPrompt(request.entry, request.context)
        : buildKpiInsightPrompt(request),
    );

    requestAnimationFrame(() => {
      const element = transcriptRef.current;

      if (element) {
        element.scrollTop = element.scrollHeight;
      }
    });
  }

  function toggleFolder(folder) {
    const wasCollapsed = collapsedFolders.has(folder);

    setCollapsedFolders((current) => {
      const next = new Set(current);

      if (next.has(folder)) {
        next.delete(folder);
      } else {
        next.add(folder);
      }

      return next;
    });

    if (!wasCollapsed) {
      return;
    }

    // Expanding: show placeholder rows first so the group reads as "opening"
    // instead of snapping in, which is hard to follow on a dense sidebar.
    window.clearTimeout(revealTimers.current.get(folder));

    setRevealingFolders((current) => new Set(current).add(folder));

    revealTimers.current.set(
      folder,
      window.setTimeout(() => {
        revealTimers.current.delete(folder);

        setRevealingFolders((current) => {
          const next = new Set(current);
          next.delete(folder);
          return next;
        });
      }, FOLDER_REVEAL_MS),
    );
  }

  function toggleSidebar() {
    setSidebarOpen((open) => {
      const next = !open;

      window.localStorage.setItem(SIDEBAR_KEY, next ? "open" : "closed");

      return next;
    });
  }

  const shellClassName = [
    "app-shell",
    isChatOpen ? "chat-open" : "chat-closed",
    sidebarOpen ? "sidebar-open" : "sidebar-collapsed",
    resizing ? "is-resizing" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // The module list is served by the backend, so the shell waits for it
  // rather than assuming which agents exist. The chrome renders immediately
  // and the two panels stand in with skeletons.
  if (agentsLoading || !currentAgent) {
    return (
      <main className={shellClassName}>
        <AppTopbar sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} />

        <div className="app-body">
          {sidebarOpen ? (
            <aside id="agent-sidebar" className="sidebar" aria-label="Agent chats">
              {/* Mirrors the loaded sidebar's header so the skeleton and the
                  real list share a top edge — otherwise the whole agent list
                  jumps once the modules arrive. Keep the two in sync. */}
              <div className="brand">
                <div className="brand-mark">
                  <img className="brand-mark-svg" src={UserIcon} alt="User" />
                </div>

                <div className="brand-copy">
                  <strong>User</strong>

                  <span>user@id.ey.com</span>
                </div>
              </div>

              {agentsError ? (
                <p className="sidebar-notice" role="alert">
                  {agentsError}
                </p>
              ) : agentsLoading ? (
                <AgentListSkeleton rows={4} />
              ) : (
                <p className="sidebar-notice">No agents are enabled.</p>
              )}
            </aside>
          ) : null}

          <section className="workboard">
            {agentsError ? (
              <div className="workboard-status error" role="alert">
                {agentsError}
              </div>
            ) : agentsLoading ? (
              <DashboardSkeleton label="Preparing your dashboard" />
            ) : (
              <div className="workboard-status" role="status">
                No agents are enabled.
              </div>
            )}
          </section>
        </div>
      </main>
    );
  }

  return (
    <main
      className={shellClassName}
      style={{
        "--chat-width": `${chatWidth}px`,
      }}
    >
      <AppTopbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={toggleSidebar}
        kicker={`${currentAgent.name} dashboard`}
        title={`${currentAgent.name} performance board`}
      >
        <AlertsPanel
          agentId={activeAgent}
          agentName={currentAgent.name}
          isChatOpen={isChatOpen}
          onToggleChat={toggleChat}
        />
      </AppTopbar>

      <div className="app-body">
        {sidebarOpen ? (
          <aside id="agent-sidebar" className="sidebar" aria-label="Agent chats">
            <div className="brand">
              <div className="brand-mark">
                <img className="brand-mark-svg" src={UserIcon} alt="User" />
              </div>

              <div className="brand-copy">
                <strong>User</strong>

                <span>user@id.ey.com</span>
              </div>
            </div>

            <nav className="agent-groups" aria-label="Choose an agent">
              {groups.map((group) => {
                const collapsed = collapsedFolders.has(group.folder);
                const revealing = revealingFolders.has(group.folder);

                return (
                  <div key={group.folder} className="agent-group">
                    <button
                      type="button"
                      className="folder-toggle"
                      aria-expanded={!collapsed}
                      aria-busy={revealing}
                      onClick={() => toggleFolder(group.folder)}
                    >
                      <span className="folder-chevron" aria-hidden="true" />

                      <span className="folder-name">{group.label}</span>

                      <span className="folder-count">{group.agents.length}</span>
                    </button>

                    {!collapsed && revealing && (
                      <AgentListSkeleton
                        rows={group.agents.length}
                        label={`Opening ${group.label}`}
                      />
                    )}

                    {!collapsed && !revealing && (
                      <div className="agent-list">
                        {group.agents.map((agent) => {
                          const chat = chats[agent.id] || EMPTY_CHAT;

                          return (
                            <button
                              key={agent.id}
                              type="button"

                              className={
                                agent.id === activeAgent
                                  ? "agent-button active"
                                  : "agent-button"
                              }

                              data-busy={chat.busy}

                              onClick={() => selectAgent(agent.id)}
                            >
                              <span className="agent-avatar">
                                {agent.name.charAt(0)}
                              </span>

                              <span className="agent-copy">
                                <strong>{agent.name}</strong>
                              </span>

                              <span className="activity-dot" aria-hidden="true" />
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </nav>
          </aside>
        ) : null}

        <Workboard
          agentId={activeAgent}
          agentName={currentAgent.name}
          onAskInsight={askKpiInsight}
          insightBusy={currentChat.busy}
          serverFilterValues={serverFilters}
          onServerFilterChange={setServerFilter}
        />

        {isChatOpen ? (
          <div
            className="chat-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize chat panel"
            aria-controls="agent-chat-panel"
            tabIndex={0}
            onMouseDown={startResize}
            onKeyDown={handleResizeKey}
          >
            <span className="chat-resize-grip" aria-hidden="true" />
          </div>
        ) : null}

        <section
          id="agent-chat-panel"
          className="chat-panel"
          aria-label={`${currentAgent.name} chat`}
        >
          <header className="chat-header">
            <div>
              <span className="header-kicker">
                {currentAgent.name} chat
                {currentChat.busy ? " · working" : ""}
              </span>

              <h1>{currentChat.title || `Ask ${currentAgent.name}`}</h1>
            </div>

            <div className="chat-header-actions">
              <div className="clear-area">
                <button
                  type="button"
                  className="clear-button"
                  disabled={!currentChat.messages.length}
                  onClick={() => setClearOpen((open) => !open)}
                >
                  Clear chat
                </button>

                {clearOpen && (
                  <div className="clear-confirm">
                    <p>Clear this agent&apos;s local messages?</p>

                    <div>
                      <button type="button" onClick={() => setClearOpen(false)}>
                        Cancel
                      </button>

                      <button
                        type="button"
                        className="danger"
                        onClick={clearCurrentChat}
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <button
                type="button"
                className="chat-close-button"
                aria-label={`Close ${currentAgent.name} chat`}
                title="Close chat"
                onClick={closeChat}
              >
                ×
              </button>
            </div>
          </header>

          <div ref={transcriptRef} className="transcript" aria-live="polite">
            {!currentChat.messages.length ? (
              <EmptyState agent={currentAgent} />
            ) : (
              <ol className="message-list">
                {currentChat.messages.map((message) => (
                  <ChatMessage
                    key={message.id}

                    message={message}

                    agentName={currentAgent.name}
                  />
                ))}
              </ol>
            )}
          </div>

          <footer className="composer-wrap">
            {visibleSuggestions?.length > 0 && (
              <section
                className="prompt-suggestions"
                aria-label="Suggested prompts"
              >
                <div className="prompt-suggestions-heading">
                  <SparkleIcon className="prompt-suggestions-spark" />

                  <span>
                    {t(
                      currentChat.messages.length > 0
                        ? "Suggested follow-ups"
                        : "Suggested prompts"
                    )}
                  </span>
                </div>

                <div className="prompt-suggestions-list">
                  {visibleSuggestions.map((suggestion) => {
                    // Shown and sent as the same words. Filling the composer
                    // with English after the reader clicked a Bahasa chip
                    // would be a visible mismatch, and asking in Bahasa is
                    // the point of the toggle. `key` stays the original so a
                    // chip keeps its identity across a language switch.
                    const label = t(suggestion);
                    return (
                      <button
                        key={suggestion}
                        type="button"
                        className="prompt-chip"
                        disabled={currentChat.busy}
                        onClick={() => {
                          setCurrentDraft(label);

                          requestAnimationFrame(() => {
                            composerRef.current?.focus();
                          });
                        }}
                      >
                        <SparkleIcon className="prompt-chip-spark" />

                        <span className="prompt-chip-text">{label}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            <form className="composer" onSubmit={sendMessage}>
              <textarea
                ref={composerRef}
                value={input}

                disabled={currentChat.busy}

                rows={1}
                maxLength={2000}

                placeholder={currentAgent.prompt}

                aria-label={`Message ${currentAgent.name}`}

                onChange={(event) => setCurrentDraft(event.target.value)}

                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();

                    event.currentTarget.form.requestSubmit();
                  }
                }}
              />

              <button type="submit" className="send-button" disabled={!canSend}>
                Send
              </button>
            </form>

            <p className="composer-note">
              AI responses should be reviewed before financial decisions are made.
            </p>
          </footer>
        </section>
      </div>

      <ProblemToasts />
    </main>
  );
}

function EmptyState({ agent }) {
  return (
    <div className="empty-state">
      <div className="empty-content">
        <div className="empty-icon">{agent.name.charAt(0)}</div>

        <h2>{agent.name}, ready when you are</h2>

        <p>{agent.description}</p>
      </div>
    </div>
  );
}

function SparkleIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="14"
      height="14"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 2.5l1.9 4.9 4.9 1.9-4.9 1.9L12 16l-1.9-4.8L5.2 9.3l4.9-1.9L12 2.5zm6.5 10l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9.9-2.3zM5 14l.75 1.95L7.7 16.7l-1.95.75L5 19.4l-.75-1.95L2.3 16.7l1.95-.75L5 14z"
      />
    </svg>
  );
}

function makeId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

function formatTime() {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date());
}

function generateTitle(message) {
  const normalized = message.replace(/\s+/g, " ").trim();

  if (normalized.length <= 42) {
    return normalized;
  }

  const clipped = normalized.slice(0, 42);

  const lastSpace = clipped.lastIndexOf(" ");

  const cutoff = lastSpace > 24 ? lastSpace : 42;

  return `${clipped.slice(0, cutoff)}...`;
}

function formatToolName(tool) {
  return String(tool || "tool").replaceAll("_", " ");
}

function buildKpiInsightPrompt(kpi) {
  const value = [kpi.value, kpi.unit].filter(Boolean).join(" ");

  const context = kpi.delta ? ` (${kpi.delta})` : "";

  return (
    `Interpret the "${kpi.label}" KPI, currently ${value}${context}. ` +
    "Why is it at this level, what are the main drivers behind it, " +
    "and what actions should I consider? Keep it concise and " +
    "decision-focused for a CFO."
  );
}
