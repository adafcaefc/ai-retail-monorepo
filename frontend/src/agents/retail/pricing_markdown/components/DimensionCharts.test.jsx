import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import { ALL, DEFAULT_SCOPE } from "../data/contract.js";
import DimensionCharts from "./DimensionCharts.jsx";

// Bar renders a clickable stub exposing whatever onClick prop it was given —
// this is what actually caught the regression where the store/state panels
// wired onClick on the chart (via Recharts' hover-tracked activePayload,
// which real Recharts never fired on a bare click) instead of on the <Bar>
// itself, the same place the working category/vertical/legal-entity charts
// wire it. A pill-only test wouldn't have caught that; this exercises the
// same onClick prop Recharts would call on a real bar click.
vi.mock("recharts", () => {
  const Empty = () => null;
  return {
    Bar: ({ dataKey, onClick }) =>
      onClick ? (
        <button
          type="button"
          data-testid={`bar-${dataKey}`}
          onClick={() => onClick({ payload: { store_id: "S001", state: "Expiry" } })}
        >
          bar
        </button>
      ) : null,
    BarChart: ({ children }) => <div>{children}</div>,
    CartesianGrid: Empty,
    Cell: Empty,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    Tooltip: Empty,
    XAxis: Empty,
    YAxis: Empty,
  };
});

beforeEach(() => {
  window.localStorage.clear();
});

function articleByTitle(title) {
  return [...document.querySelectorAll("article")].find(
    (article) => article.querySelector("h3")?.textContent === title,
  );
}

const byStore = [
  { store_id: "S001", label: "Grocery 01 · Jakarta Pusat", cluster: "Express", channel: "Physical", expiry_count: 2, overstock_count: 0, slow_mover_count: 1, other_count: 5, sku_count: 8, at_risk_value: 100 },
];
const byCluster = [{ cluster: "Express", label: "Express", value: 100, store_count: 1 }];
const byChannel = [{ channel: "Physical", label: "Physical", value: 100, store_count: 1 }];
const byState = [{ state: "Expiry", value: 100 }];
const byLegalEntity = [{ legal_entity_id: "GRC", label: "Grocery Retail", value: 100 }];

function renderCharts(props = {}) {
  return render(
    <LanguageProvider>
      <DimensionCharts
        byStore={byStore}
        byCluster={byCluster}
        byChannel={byChannel}
        byState={byState}
        byLegalEntity={byLegalEntity}
        scope={{ ...DEFAULT_SCOPE }}
        onSelectStore={vi.fn()}
        onSelectState={vi.fn()}
        onSelectLegalEntity={vi.fn()}
        {...props}
      />
    </LanguageProvider>,
  );
}

describe("store dimension panel — click to filter", () => {
  it("hides the reset button when store scope is ALL", () => {
    renderCharts();
    expect(screen.queryByText("Back to all stores")).not.toBeInTheDocument();
  });

  it("shows the reset button once a store is selected, and resets on click", () => {
    const onSelectStore = vi.fn();
    renderCharts({ scope: { ...DEFAULT_SCOPE, store_id: "S001" }, onSelectStore });

    fireEvent.click(screen.getByText("Back to all stores"));
    expect(onSelectStore).toHaveBeenCalledWith(ALL);
  });

  it("renders a filter-shortcut pill per store row, calling onSelectStore with the store id", () => {
    const onSelectStore = vi.fn();
    renderCharts({ onSelectStore });

    fireEvent.click(screen.getByRole("button", { name: "Grocery 01 · Jakarta Pusat" }));
    expect(onSelectStore).toHaveBeenCalledWith("S001");
  });

  // Regression: the store chart used to wire onClick on <BarChart> (chart-level),
  // relying on Recharts' hover-tracked activePayload, which a real click never
  // populated — only the pills worked. Each stacked <Bar> now carries its own
  // onClick, same as the working category/vertical/legal-entity charts.
  it("clicking a bar segment (not just the pill row) calls onSelectStore with the store id", () => {
    const onSelectStore = vi.fn();
    renderCharts({ onSelectStore });
    const storePanel = articleByTitle("At-risk value by store");

    fireEvent.click(within(storePanel).getByTestId("bar-expiry_count"));
    expect(onSelectStore).toHaveBeenCalledWith("S001");
  });
});

describe("state dimension panel — click to filter", () => {
  it("shows the reset button once a state is selected, and resets on click", () => {
    const onSelectState = vi.fn();
    renderCharts({ scope: { ...DEFAULT_SCOPE, state: "Expiry" }, onSelectState });

    fireEvent.click(screen.getByText("Back to all states"));
    expect(onSelectState).toHaveBeenCalledWith(ALL);
  });

  it("renders a filter-shortcut pill per state row, calling onSelectState with the state", () => {
    const onSelectState = vi.fn();
    renderCharts({ onSelectState });

    fireEvent.click(screen.getByRole("button", { name: "Expiry" }));
    expect(onSelectState).toHaveBeenCalledWith("Expiry");
  });

  // Regression: same chart-level-onClick bug as the store panel above.
  it("clicking the bar (not just the pill row) calls onSelectState with the state", () => {
    const onSelectState = vi.fn();
    renderCharts({ onSelectState });
    const statePanel = articleByTitle("Inventory value by state");

    fireEvent.click(within(statePanel).getByTestId("bar-value"));
    expect(onSelectState).toHaveBeenCalledWith("Expiry");
  });
});

describe("legal entity dimension panel — click to filter", () => {
  it("shows the reset button once a legal entity is selected, and resets on click", () => {
    const onSelectLegalEntity = vi.fn();
    renderCharts({ scope: { ...DEFAULT_SCOPE, legal_entity_id: "GRC" }, onSelectLegalEntity });

    fireEvent.click(screen.getByText("Back to all legal entities"));
    expect(onSelectLegalEntity).toHaveBeenCalledWith(ALL);
  });

  it("renders a filter-shortcut pill per legal entity row, calling onSelectLegalEntity with the id", () => {
    const onSelectLegalEntity = vi.fn();
    renderCharts({ onSelectLegalEntity });

    fireEvent.click(screen.getByRole("button", { name: "Grocery Retail" }));
    expect(onSelectLegalEntity).toHaveBeenCalledWith("GRC");
  });
});

describe("cluster and channel dimension panels", () => {
  it("render no reset button or filter pills — cluster/channel aren't scope fields", () => {
    renderCharts();
    expect(screen.queryByText(/Back to all/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Express" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Physical" })).not.toBeInTheDocument();
  });
});
