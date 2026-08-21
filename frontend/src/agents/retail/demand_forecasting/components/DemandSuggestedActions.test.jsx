import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import DemandSuggestedActions from "./DemandSuggestedActions.jsx";

function row(overrides = {}) {
  return {
    store_id: "S001",
    store_name: "Grocery 01",
    sku_id: "GRC-001",
    item_name: "Rice 5kg",
    category_id: "GRC-C01",
    category: "Grocery",
    target: { value: 12.3, unit: "units/day", basis: "ads" },
    forecast_7d: 86.1,
    rop: 20,
    max: 35,
    position: 14,
    suggestion: 21,
    signal: ["below_rop", "viral"],
    route: "direct",
    lead_time_days: 2,
    eta: null,
    eta_status: "unavailable",
    perishable: false,
    vendor: "Vendor A",
    ...overrides,
  };
}

function payload(rows = [
  row(),
  row({ sku_id: "GRC-002", item_name: "Tea", suggestion: 0, position: 23, signal: ["growth"], route: "flow" }),
  row({ store_id: "S002", store_name: "Grocery 02", sku_id: "GRC-003", suggestion: 5, signal: ["promo"], route: "cross" }),
], scope = { legal_entity_id: null, category_group: null, store_id: null, sku: null }) {
  return {
    schema_version: 1,
    agent: "retail.demand_forecasting",
    as_of: "2026-07-01",
    scope,
    grain: "sku_store",
    source: "retail.fact_inventory_daily.forecast_7d",
    source_import_batch_id: 23,
    row_count: rows.length,
    action_row_count: rows.filter((item) => item.suggestion > 0).length,
    dashboard_forecast_7d: 123.5,
    basket_forecast_7d: 123.5,
    reconciles: true,
    suggestion_units: rows.reduce((total, item) => total + item.suggestion, 0),
    rows,
  };
}

function handoff(status, id = "handoff-1") {
  return {
    handoff_id: id,
    source_agent: "retail.demand_forecasting",
    target_agent: "retail.replenishment",
    handoff_type: "forecast_basket",
    status,
    scope: {
      legal_entity_id: null,
      category_group: null,
      store_id: null,
      sku: null,
    },
    source_snapshot_date: "2026-07-01",
    source_import_batch_id: 23,
    basket_hash: "a".repeat(64),
  };
}

function renderComponent(query = {}) {
  return render(
    <LanguageProvider>
      <DemandSuggestedActions query={query} />
    </LanguageProvider>,
  );
}

function workflowStatus() {
  return document.querySelector(".demand-workflow-status strong");
}

describe("DemandSuggestedActions", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => payload() }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not fetch until Generate forecast basket is activated", async () => {
    renderComponent();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Send 7-day forecast basket to Replenishment")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await screen.findByText("Forecast KPI reconciled");
  });

  it("shows loading, sends only the four current scope filters, and renders live totals", async () => {
    let resolveRequest;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { resolveRequest = resolve; }));
    renderComponent({
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
      store_id: "S001",
      sku: "GRC-00",
      grain: "monthly",
      horizon_weeks: 16,
    });

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    expect(screen.getByText("Generating forecast basket…")).toBeInTheDocument();

    const url = new URL(fetchMock.mock.calls[0][0], window.location.origin);
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
      store_id: "S001",
      sku: "GRC-00",
    });
    expect(url.search).not.toContain("grain");
    expect(url.search).not.toContain("horizon");

    resolveRequest({ ok: true, status: 200, json: async () => payload() });
    await screen.findByText("Forecast KPI reconciled");
    expect(screen.getByText("123.5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("26")).toBeInTheDocument();
  });

  it("does not present a non-reconciling response as a ready basket", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ...payload(), reconciles: false }),
    });
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "does not reconcile to the dashboard KPI",
    );
    expect(screen.queryByText("Forecast KPI reconciled")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("defaults to actionable rows, exposes all rows, and presents route, signals, and ETA honestly", async () => {
    renderComponent();
    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");

    const table = screen.getByRole("table");
    expect(within(table).getByText("GRC-001")).toBeInTheDocument();
    expect(within(table).queryByText("GRC-002")).not.toBeInTheDocument();
    expect(within(table).getByText("viral")).toBeInTheDocument();
    expect(within(table).getByText("direct")).toBeInTheDocument();
    expect(within(table).getAllByText("Unavailable").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "All rows" }));
    expect(within(screen.getByRole("table")).getByText("GRC-002")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("growth")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("flow")).toBeInTheDocument();
  });

  it("hides Store for a selected Store scope and clears a generated snapshot when scope changes", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload(undefined, {
        legal_entity_id: null,
        category_group: null,
        store_id: "S001",
        sku: null,
      }),
    });
    const view = renderComponent({ store_id: "S001" });
    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");

    expect(within(screen.getByRole("table")).queryByRole("columnheader", { name: "Store" })).not.toBeInTheDocument();
    expect(screen.getByText("123.5")).toBeInTheDocument();

    view.rerender(
      <LanguageProvider>
        <DemandSuggestedActions query={{ store_id: "S002" }} />
      </LanguageProvider>,
    );
    await waitFor(() => expect(screen.queryByText("Forecast KPI reconciled")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Generate forecast basket" })).toBeEnabled();
  });

  it("keeps a large all-row basket paginated instead of mounting every row", async () => {
    const rows = Array.from({ length: 250 }, (_, index) => row({
      sku_id: `GRC-${String(index + 1).padStart(3, "0")}`,
      suggestion: index % 2 ? 0 : 1,
    }));
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload(rows) });
    renderComponent();
    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");
    fireEvent.click(screen.getByRole("button", { name: "All rows" }));

    expect(screen.getByRole("table").querySelectorAll("tbody tr")).toHaveLength(100);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
  });

  it("does not make workflow controls look like successful persisted actions", async () => {
    renderComponent();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reopen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Flag to Agent 2 · Inventory Risk" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" })).toBeDisabled();
    expect(workflowStatus()).toHaveTextContent("Not generated");
  });

  it("persists approval before enabling Send and sends only server-confirmed status", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload() });
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("approved") }) });
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Approved"));
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" })).toBeEnabled();

    const request = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(request.source_agent).toBe("retail.demand_forecasting");
    expect(request.target_agent).toBe("retail.replenishment");
    expect(request.handoff_type).toBe("forecast_basket");
    expect(request.expected.row_count).toBe(3);
    expect(request).not.toHaveProperty("rows");
  });

  it("uses server transitions for reject, reopen, approve, and send", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload() })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("rejected") }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("reopened") }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("approved") }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("sent") }) });
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Rejected"));
    expect(screen.getByRole("button", { name: "Reopen" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Reopened"));
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Approved"));
    fireEvent.click(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Sent"));
    expect(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" })).toBeDisabled();

    expect(fetchMock.mock.calls[2][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ status: "reopened" });
    expect(fetchMock.mock.calls[4][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({ status: "sent" });
  });

  it("keeps the prior status when persistence fails and flags Agent 2 only after delivery", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload() })
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: "Regenerate the forecast basket." }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: { ...handoff("sent", "risk-1"), target_agent: "retail.inventory_risk", handoff_type: "risk_flag" } }) });
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Regenerate the forecast basket");
    expect(workflowStatus()).toHaveTextContent("Pending decision");
    expect(screen.getByRole("button", { name: "Send to Agent 3 · Replenishment" })).toBeDisabled();

    const flag = screen.getByRole("button", { name: "Flag to Agent 2 · Inventory Risk" });
    expect(flag).toBeEnabled();
    fireEvent.click(flag);
    await screen.findByText("Delivered to the Inventory Risk inbox for review.");
    expect(screen.getByRole("button", { name: "Flag to Agent 2 · Inventory Risk" })).toBeDisabled();
    const flagRequest = JSON.parse(fetchMock.mock.calls[2][1].body);
    expect(flagRequest.target_agent).toBe("retail.inventory_risk");
    expect(flagRequest.handoff_type).toBe("risk_flag");
  });

  it("disconnects persisted workflow state when the filter scope changes", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload() })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ handoff: handoff("approved") }) });
    const view = renderComponent({ category_group: "GRC-C01" });
    fireEvent.click(screen.getByRole("button", { name: "Generate forecast basket" }));
    await screen.findByText("Forecast KPI reconciled");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Approved"));

    view.rerender(
      <LanguageProvider>
        <DemandSuggestedActions query={{ category_group: "BEV-C01" }} />
      </LanguageProvider>,
    );

    await waitFor(() => expect(workflowStatus()).toHaveTextContent("Not generated"));
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
