import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  approveAction: vi.fn(),
  fetchActions: vi.fn(),
  fetchAgents: vi.fn(),
  fetchAlertsWithActions: vi.fn(),
  fetchDashboard: vi.fn(),
  fetchMonitoringAgents: vi.fn(),
  recalculateDashboardSimulation: vi.fn(),
  simulateAction: vi.fn(),
  streamChat: vi.fn(),
  monitoring: {
    status: "idle",
    error: "",
    note: "",
    runId: 0,
    isRunning: false,
    recalculate: vi.fn(),
    problems: [],
    moreProblems: 0,
    dismissProblem: vi.fn(),
  },
}));

vi.mock("./api/agents.js", () => ({
  fetchAgents: mocks.fetchAgents,
}));

vi.mock("./api/alerts.js", () => ({
  approveAction: mocks.approveAction,
  fetchActions: mocks.fetchActions,
  fetchAlertsWithActions: mocks.fetchAlertsWithActions,
  fetchMonitoringAgents: mocks.fetchMonitoringAgents,
  simulateAction: mocks.simulateAction,
}));

vi.mock("./api/chatStream.js", () => ({
  streamChat: mocks.streamChat,
}));

vi.mock("./api/dashboard.js", () => ({
  fetchDashboard: mocks.fetchDashboard,
  recalculateDashboardSimulation: mocks.recalculateDashboardSimulation,
}));

vi.mock("./monitoring/MonitoringProvider.jsx", () => ({
  MonitoringProvider: ({ children }) => children,
  useMonitoring: () => mocks.monitoring,
}));

import App from "./App.jsx";
import { AgentsProvider } from "./agents/AgentsProvider.jsx";

const AGENTS = [
  {
    id: "finance.finance",
    folder: "finance",
    display: "Finance",
    description: "Explore financial performance and plan variances.",
    prompt: "Ask Finance about performance...",
    starter_prompts: ["Explain finance performance."],
    dashboard_only: false,
  },
  {
    id: "finance.treasury",
    folder: "finance",
    display: "Treasury",
    description: "Review liquidity and cash-flow forecasts.",
    prompt: "Ask Treasury about liquidity...",
    starter_prompts: ["Explain treasury performance."],
    dashboard_only: false,
  },
  {
    id: "finance.collection",
    folder: "finance",
    display: "Collection",
    description: "Review receivables.",
    prompt: "Ask Collection about receivables...",
    starter_prompts: [],
    dashboard_only: false,
  },
  {
    id: "finance.leakage",
    folder: "finance",
    display: "Leakage",
    description: "Review payment leakage.",
    prompt: "Ask Leakage about exposure...",
    starter_prompts: [],
    dashboard_only: false,
  },
  {
    id: "retail.retail",
    folder: "retail",
    display: "Retail",
    description: "Review retail performance, trends, and operational insights.",
    prompt: "Retail chat is not connected yet.",
    starter_prompts: [
      "Summarize retail performance trends.",
      "Which retail operations need attention?",
    ],
    dashboard_only: true,
  },
];

function emptyDashboard(agent) {
  return {
    agent,
    default_view: "",
    kpis: [],
    views: {},
    side: {},
    filters: [],
    simulator: null,
  };
}

function renderApp() {
  return render(
    <AgentsProvider>
      <App />
    </AgentsProvider>,
  );
}

async function selectAgent(name) {
  await waitFor(() => {
    expect(document.querySelectorAll(".agent-button").length).toBe(5);
  });

  const button = [...document.querySelectorAll(".agent-button")].find(
    (candidate) => candidate.querySelector("strong")?.textContent === name,
  );

  expect(button).toBeDefined();
  fireEvent.click(button);
  await screen.findByRole("heading", { name: `${name} performance board` });
  return button;
}

function calledWithAgent(mock, agentId) {
  return mock.mock.calls.some(([value]) => value === agentId);
}

describe("Retail dashboard and frontend-only chat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();

    mocks.fetchAgents.mockResolvedValue(AGENTS);
    mocks.fetchAlertsWithActions.mockResolvedValue({ items: [] });
    mocks.fetchMonitoringAgents.mockResolvedValue({ items: [] });
    mocks.fetchActions.mockResolvedValue({ items: [] });
    mocks.fetchDashboard.mockImplementation(async (agent) =>
      emptyDashboard(agent),
    );
    mocks.streamChat.mockResolvedValue(undefined);
  });

  it("shows the standard Retail controls and opens a backend-safe Retail chat", async () => {
    renderApp();
    await screen.findByRole("button", { name: "Ask Finance" });

    const retailButton = await selectAgent("Retail");

    expect(retailButton).toHaveClass("active");
    expect(screen.getByText("Retail dashboard")).toBeInTheDocument();

    // The board toolbar is icon-first: only the primary action carries a
    // caption, so Recalculate and the overflow menu are matched on their
    // labels. Subagents and Audit History live behind that menu now, and
    // disabling its trigger is what puts them out of reach.
    const disabledControls = [
      "Agent Action",
      "Recalculate this board",
      "More board tools",
    ].map((label) => screen.getByRole("button", { name: label }));

    for (const control of disabledControls) {
      expect(control).toBeDisabled();
      fireEvent.click(control);
    }

    // Clicking the trigger above did nothing, so the menu never mounted.
    expect(screen.queryByRole("menuitem", { name: /Subagents/ })).toBeNull();
    expect(
      screen.queryByRole("menuitem", { name: "Audit History" }),
    ).toBeNull();

    const notifications = screen.getByRole("button", {
      name: "Retail notifications unavailable",
    });
    expect(notifications).toBeDisabled();
    fireEvent.click(notifications);

    const askRetail = screen.getByRole("button", { name: "Ask Retail" });
    expect(askRetail).toBeEnabled();
    fireEvent.click(askRetail);

    expect(document.querySelector("main")).toHaveClass("chat-open");
    expect(askRetail).toHaveClass("on");
    expect(screen.getByText("Retail chat")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask Retail" })).toBeInTheDocument();
    expect(screen.getByText("Retail, ready when you are")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Review retail performance, trends, and operational insights.",
      ),
    ).toBeInTheDocument();
    expect(document.querySelector(".empty-icon")).toHaveTextContent("R");

    const retailDashboard = screen.getByTestId("retail-dashboard");
    expect(retailDashboard).toBeEmptyDOMElement();

    const input = screen.getByRole("textbox", { name: "Message Retail" });
    const send = screen.getByRole("button", { name: "Send" });
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute("placeholder", "Retail chat is not connected yet.");
    expect(send).toBeDisabled();

    for (const prompt of AGENTS.at(-1).starter_prompts) {
      expect(screen.getByRole("button", { name: prompt })).toBeDisabled();
    }

    fireEvent.submit(input.closest("form"));
    expect(mocks.streamChat).not.toHaveBeenCalled();

    for (const requestMock of [
      mocks.fetchDashboard,
      mocks.fetchAlertsWithActions,
      mocks.fetchMonitoringAgents,
      mocks.fetchActions,
    ]) {
      expect(calledWithAgent(requestMock, "retail.retail")).toBe(false);
    }
    expect(mocks.monitoring.recalculate).not.toHaveBeenCalled();
    expect(mocks.simulateAction).not.toHaveBeenCalled();
    expect(mocks.approveAction).not.toHaveBeenCalled();

    fireEvent.click(document.querySelector(".chat-close-button"));
    expect(document.querySelector("main")).toHaveClass("chat-closed");
    expect(retailButton).toHaveClass("active");
    expect(retailDashboard).toBeInTheDocument();
  });

  it("keeps Finance and Treasury chat execution on their own agent ids", async () => {
    renderApp();

    const askFinance = await screen.findByRole("button", { name: "Ask Finance" });
    fireEvent.click(askFinance);

    let input = screen.getByRole("textbox", { name: "Message Finance" });
    fireEvent.change(input, { target: { value: "Finance question" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => {
      expect(mocks.streamChat).toHaveBeenCalledWith(
        expect.objectContaining({ agent: "finance.finance" }),
      );
    });

    await selectAgent("Treasury");
    expect(document.querySelector(".chat-toggle-btn")).toHaveClass("on");
    expect(document.querySelector(".chat-toggle-btn")).toHaveAttribute(
      "aria-label",
      "Close Treasury chat",
    );
    expect(screen.getByRole("heading", { name: "Ask Treasury" })).toBeInTheDocument();

    input = screen.getByRole("textbox", { name: "Message Treasury" });
    fireEvent.change(input, { target: { value: "Treasury question" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => {
      expect(mocks.streamChat).toHaveBeenCalledWith(
        expect.objectContaining({ agent: "finance.treasury" }),
      );
    });

    await selectAgent("Retail");
    expect(screen.getByRole("heading", { name: "Ask Retail" })).toBeInTheDocument();
    expect(screen.getByText("Retail, ready when you are")).toBeInTheDocument();
    expect(screen.queryByText("Treasury, ready when you are")).not.toBeInTheDocument();
    expect(mocks.streamChat).toHaveBeenCalledTimes(2);
  });
});
