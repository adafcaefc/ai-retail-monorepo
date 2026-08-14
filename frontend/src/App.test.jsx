import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  approveAction: vi.fn(),
  fetchActions: vi.fn(),
  fetchAgents: vi.fn(),
  fetchAlertsWithActions: vi.fn(),
  fetchDashboard: vi.fn(),
  fetchFormulas: vi.fn(),
  fetchMonitoringAgents: vi.fn(),
  fetchSheetList: vi.fn(),
  fetchSheetPage: vi.fn(),
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

// The Data Source page imports this at module load, via the page registry, so
// it has to be mocked even for the tests that never open that page.
vi.mock("./api/excel.js", () => ({
  fetchSheetList: mocks.fetchSheetList,
  fetchSheetPage: mocks.fetchSheetPage,
}));

// Formula Manager is the default screen, so its loader runs on every render.
vi.mock("./api/formulas.js", () => ({
  createFormula: vi.fn(),
  deleteFormula: vi.fn(),
  evaluateFormula: vi.fn(),
  fetchFormulas: mocks.fetchFormulas,
  updateFormula: vi.fn(),
  validateFormula: vi.fn(),
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
    id: "retail.demand_forecasting",
    folder: "retail",
    display: "Demand Forecasting",
    description: "Review retail demand forecasts.",
    prompt: "Ask Demand...",
    starter_prompts: [],
    dashboard_only: true,
  },
  {
    id: "retail.inventory_risk",
    folder: "retail",
    display: "Inventory Risk",
    description: "Review retail inventory risk.",
    prompt: "Ask Inventory...",
    starter_prompts: [],
    dashboard_only: true,
  },
  {
    id: "retail.replenishment",
    folder: "retail",
    display: "Replenishment",
    description: "Review retail replenishment needs.",
    prompt: "Ask Replenishment...",
    starter_prompts: [],
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

// The static pages in src/pages are prepended to the agent list, so every
// sidebar count here is "agents plus pages".
// What If Simulator and Data Source are currently hidden (see
// docs/DISABLED_FEATURES.md), leaving only Formula Manager.
const PAGE_COUNT = 1;

// One window of a sheet, shaped exactly like GET /api/excel/sheets/{name}.
const SHEET_LIST = {
  workbook: "sample.xlsx",
  count: 2,
  sheets: [
    { index: 0, name: "Cover & Storyline", row_count: 3, column_count: 3 },
    { index: 1, name: "ENGINE_STORE", row_count: 16003, column_count: 3 },
  ],
};

const SHEET_PAGE = {
  sheet: "Cover & Storyline",
  index: 0,
  offset: 0,
  limit: 100,
  row_count: 3,
  column_count: 3,
  returned_rows: 2,
  has_more: false,
  columns: [
    { index: 1, letter: "A", width_px: 66 },
    { index: 2, letter: "B", width_px: 66 },
    { index: 3, letter: "C", width_px: 66 },
  ],
  merges: [
    { row: 1, column: 1, rowspan: 1, colspan: 3, clipped: false },
  ],
  rows: [
    {
      row: 1,
      cells: [
        { v: "AI RETAIL 360", b: true, fg: "#FFFFFF", bg: "#1E3A5F" },
        null,
        null,
      ],
    },
    {
      row: 2,
      cells: [{ v: "Units" }, { v: "12,480", t: "n" }, null],
    },
  ],
};

function renderApp() {
  return render(
    <AgentsProvider>
      <App />
    </AgentsProvider>,
  );
}

function agentButtons() {
  return [...document.querySelectorAll(".agent-button")];
}

function buttonNamed(name) {
  return agentButtons().find(
    (candidate) => candidate.querySelector("strong")?.textContent === name,
  );
}

async function waitForSidebar() {
  await waitFor(() => {
    expect(document.querySelectorAll(".agent-button").length).toBe(
      AGENTS.length + PAGE_COUNT,
    );
  });
}

async function selectAgent(name) {
  await waitForSidebar();

  const button = buttonNamed(name);

  expect(button).toBeDefined();
  fireEvent.click(button);
  const agent = AGENTS.find((item) => item.display === name);
  const title =
    agent?.folder === "retail" ? name : `${name} performance board`;
  await screen.findByRole("heading", { name: title });
  return button;
}

function calledWithAgent(mock, agentId) {
  return mock.mock.calls.some(([value]) => value === agentId);
}

describe("Retail dashboard and frontend-only chat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    // The hash is the app's only route, so a test that sets one must not leak
    // it into the next.
    window.location.hash = "";

    mocks.fetchAgents.mockResolvedValue(AGENTS);
    mocks.fetchAlertsWithActions.mockResolvedValue({ items: [] });
    mocks.fetchMonitoringAgents.mockResolvedValue({ items: [] });
    mocks.fetchActions.mockResolvedValue({ items: [] });
    mocks.fetchDashboard.mockImplementation(async (agent) =>
      emptyDashboard(agent),
    );
    mocks.streamChat.mockResolvedValue(undefined);
    mocks.fetchSheetList.mockResolvedValue(SHEET_LIST);
    mocks.fetchSheetPage.mockResolvedValue(SHEET_PAGE);
    mocks.fetchFormulas.mockResolvedValue({ items: [], count: 0 });
  });

  it("opens on the Main section's first static page, without any agent chrome", async () => {
    renderApp();
    await waitForSidebar();

    // Main leads the sidebar and holds every static page.
    const folders = [...document.querySelectorAll(".folder-name")].map(
      (node) => node.textContent,
    );
    expect(folders[0]).toBe("Main");

    const pages = agentButtons()
      .slice(0, PAGE_COUNT)
      .map((button) => button.querySelector("strong").textContent);

    // Data Source and What If Simulator are hidden (docs/DISABLED_FEATURES.md),
    // so Formula Manager is currently the only static page. These assertions
    // return once Data Source is re-enabled:
    // expect(pages).toContain("Data Source");
    // expect(pages[pages.length - 1]).toBe("Data Source");
    // expect(pages[0]).not.toBe("Data Source");

    // The leading page is the default screen: page body plus a plain topbar
    // that names the section rather than calling it a performance board.
    expect(pages[0]).toBe("Formula Manager");
    expect(buttonNamed("Formula Manager")).toHaveClass("active");
    expect(screen.getByTestId("formula-manager")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Formula Manager" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Formula Manager" }),
    ).toBeInTheDocument();
    expect(document.querySelector(".header-kicker")).toHaveTextContent("Main");
    expect(
      screen.queryByRole("heading", {
        name: "Formula Manager performance board",
      }),
    ).not.toBeInTheDocument();

    // None of the agent chrome comes along, and the shell keeps its
    // two-column layout rather than reserving an empty chat track.
    expect(document.querySelector(".chat-panel")).toBeNull();
    expect(document.querySelector(".chat-resize-handle")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Ask / })).not.toBeInTheDocument();
    expect(screen.queryByText("Agent Action")).not.toBeInTheDocument();
    expect(document.querySelector("main")).toHaveClass("chat-closed");

    // A page has no backend *module*, so none of the agent APIs are called for
    // it. (Formula Manager still owns /api/formulas -- that is a page's own
    // endpoint, not an agent request.)
    for (const requestMock of [
      mocks.fetchDashboard,
      mocks.fetchAlertsWithActions,
      mocks.fetchActions,
    ]) {
      expect(calledWithAgent(requestMock, "main.formula_manager")).toBe(false);
      expect(calledWithAgent(requestMock, "main.what_if_simulator")).toBe(false);
    }
  });

  // Data Source is hidden (see docs/DISABLED_FEATURES.md); re-enable it there
  // to bring this test back.
  it.skip("renders the Data Source viewer with the workbook's own formatting", async () => {
    renderApp();
    await waitForSidebar();

    fireEvent.click(buttonNamed("Data Source"));
    expect(await screen.findByTestId("data-source")).toBeInTheDocument();

    // Every sheet is reachable from one switcher rather than a tab strip —
    // the real workbook has 49 of them.
    const sheetPicker = screen.getAllByRole("combobox")[0];
    await waitFor(() => {
      expect([...sheetPicker.options].map((option) => option.value)).toEqual([
        "Cover & Storyline",
        "ENGINE_STORE",
      ]);
    });

    // The workbook's own bold/fill/colour arrive per cell and are applied
    // inline, and its merged banner spans the row it merges.
    const banner = await screen.findByText("AI RETAIL 360");
    expect(banner.tagName).toBe("TD");
    expect(banner).toHaveAttribute("colspan", "3");
    expect(banner).toHaveStyle({
      backgroundColor: "#1E3A5F",
      color: "#FFFFFF",
      fontWeight: "600",
    });

    // A number keeps the backend's formatting and is right-aligned.
    expect(screen.getByText("12,480")).toHaveClass("is-number");

    // Paging is server-side: ENGINE_STORE is 16,003 rows.
    mocks.fetchSheetPage.mockResolvedValue({
      ...SHEET_PAGE,
      sheet: "ENGINE_STORE",
      row_count: 16003,
      has_more: true,
    });

    // Switching sheets goes back to the first row rather than carrying the
    // previous sheet's offset over.
    fireEvent.change(sheetPicker, { target: { value: "ENGINE_STORE" } });
    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("ENGINE_STORE", {
        offset: 0,
        limit: 100,
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("ENGINE_STORE", {
        offset: 100,
        limit: 100,
      });
    });
  });

  // Data Source is hidden (see docs/DISABLED_FEATURES.md); re-enable it there
  // to bring this test back.
  it.skip("opens the worksheet a cell deep link names, not the default page", async () => {
    // The hash is the whole router: the Formula Manager's cell citations link
    // here rather than to the page's front door.
    window.location.hash = "#main.data_source?cell=ENGINE_STORE%21J4";

    renderApp();

    expect(await screen.findByTestId("data-source")).toBeInTheDocument();
    expect(screen.queryByTestId("formula-manager")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(buttonNamed("Data Source")).toHaveClass("active");
    });

    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("ENGINE_STORE", {
        offset: 0,
        limit: 100,
      });
    });

    // Leaving through the sidebar drops the hash, so clicking the same
    // citation again still fires a hashchange.
    fireEvent.click(buttonNamed("Formula Manager"));
    expect(window.location.hash).toBe("");
  });

  /*
   * Both sides of the merge renamed this test, and both names had gone stale.
   * "scaffolds" stopped being true once Replenishment started rendering a real
   * purchase order, and naming only the controls drops what the loop below
   * spends most of its length on: that the three boards are independently
   * selectable and each renders its own.
   */
  it("switches between three Retail boards, every write control disabled", async () => {
    renderApp();

    await waitForSidebar();

    const retailGroup = [...document.querySelectorAll(".agent-group")].find(
      (group) => group.querySelector(".folder-name")?.textContent === "Retail",
    );
    expect(retailGroup).toBeDefined();
    expect(retailGroup.querySelector(".folder-count")).toHaveTextContent("3");
    expect(buttonNamed("Retail")).toBeUndefined();

    const retailModules = [
      {
        id: "retail.demand_forecasting",
        name: "Demand Forecasting",
        chatLabel: "Demand",
        prompt: "Ask Demand...",
      },
      {
        id: "retail.inventory_risk",
        name: "Inventory Risk",
        chatLabel: "Inventory",
        prompt: "Ask Inventory...",
      },
      {
        id: "retail.replenishment",
        name: "Replenishment",
        chatLabel: "Replenishment",
        prompt: "Ask Replenishment...",
      },
    ];

    const demandButton = await selectAgent("Demand Forecasting");
    expect(demandButton).toHaveClass("active");

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
      name: "Demand Forecasting notifications unavailable",
    });
    expect(notifications).toBeDisabled();
    fireEvent.click(notifications);

    const askDemand = screen.getByRole("button", { name: "Ask Demand" });
    expect(askDemand).toBeEnabled();
    fireEvent.click(askDemand);

    expect(document.querySelector("main")).toHaveClass("chat-open");
    expect(askDemand).toHaveClass("on");

    for (const module of retailModules) {
      const activeButton = await selectAgent(module.name);

      expect(activeButton).toHaveClass("active");
      for (const other of retailModules.filter((item) => item.id !== module.id)) {
        expect(buttonNamed(other.name)).not.toHaveClass("active");
      }

      expect(
        document.querySelector(".topbar-heading .header-kicker"),
      ).toHaveTextContent("Retail");
      expect(
        document.querySelector(".topbar-heading").children[0],
      ).toHaveTextContent("Retail");
      expect(
        document.querySelector(".topbar-heading").children[1],
      ).toHaveTextContent(module.name);
      expect(
        screen.getByRole("heading", { level: 1, name: module.name }),
      ).toBeInTheDocument();
      expect(document.querySelector(".chat-toggle-label")).toHaveTextContent(
        `Ask ${module.chatLabel}`,
      );

      expect(
        screen.getByRole("heading", { name: `Ask ${module.chatLabel}` }),
      ).toBeInTheDocument();

      if (module.id === "retail.demand_forecasting") {
        const demandDashboard = await screen.findByTestId("demand-forecasting-dashboard");
        expect(demandDashboard).toContainElement(
          screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }),
        );
        expect(document.querySelectorAll(".demand-kpi")).toHaveLength(6);
      } else if (module.id === "retail.inventory_risk") {
        await screen.findByTestId("inventory-risk-dashboard");
        expect(await screen.findByText("Inventory risk register")).toBeInTheDocument();
        expect(document.querySelectorAll(".risk-kpi")).toHaveLength(6);
      } else {
        // All three now read the same workbook. Replenishment was the last
        // blank scaffold; it renders a purchase order rather than an empty
        // section.
        await screen.findByTestId("replenishment-dashboard");
        expect(await screen.findByText("Purchase order preview")).toBeInTheDocument();
        expect(document.querySelectorAll(".po-kpi")).toHaveLength(6);
      }

      const input = screen.getByRole("textbox", {
        name: `Message ${module.name}`,
      });
      expect(input).toBeDisabled();
      expect(input).toHaveAttribute("placeholder", module.prompt);
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

      fireEvent.submit(input.closest("form"));

      for (const requestMock of [
        mocks.fetchDashboard,
        mocks.fetchAlertsWithActions,
        mocks.fetchMonitoringAgents,
        mocks.fetchActions,
      ]) {
        expect(calledWithAgent(requestMock, module.id)).toBe(false);
      }
    }

    expect(mocks.streamChat).not.toHaveBeenCalled();
    expect(mocks.monitoring.recalculate).not.toHaveBeenCalled();
    expect(mocks.simulateAction).not.toHaveBeenCalled();
    expect(mocks.approveAction).not.toHaveBeenCalled();

    fireEvent.click(document.querySelector(".chat-close-button"));
    expect(document.querySelector("main")).toHaveClass("chat-closed");
    expect(buttonNamed("Replenishment")).toHaveClass("active");
    expect(screen.getByTestId("replenishment-dashboard")).toBeInTheDocument();
    // All three Retail modules now render a full board off the same workbook,
    // so this walk costs roughly 12s in jsdom. It relies on the raised
    // `testTimeout` in vitest.config.js rather than being trimmed: the point
    // of the test is that selecting any module leaves the other two alone,
    // which needs all three.
  });

  it("keeps Finance and Treasury chat execution on their own agent ids", async () => {
    renderApp();
    await selectAgent("Finance");

    const askFinance = screen.getByRole("button", { name: "Ask Finance" });
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

    await selectAgent("Demand Forecasting");
    expect(screen.getByRole("heading", { name: "Ask Demand" })).toBeInTheDocument();
    expect(
      screen.getByText("Demand Forecasting, ready when you are"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Treasury, ready when you are")).not.toBeInTheDocument();
    expect(mocks.streamChat).toHaveBeenCalledTimes(2);
  });
});
