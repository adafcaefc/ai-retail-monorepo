import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../LanguageProvider.jsx";
import AgentHandoffInbox from "./AgentHandoffInbox.jsx";

const item = {
  handoff_id: "handoff-1",
  source_agent: "retail.demand_forecasting",
  target_agent: "retail.replenishment",
  handoff_type: "forecast_basket",
  status: "sent",
  scope: { legal_entity_id: "GRC", category_group: null, store_id: null, sku: null },
  as_of: "2026-07-01",
  basket_hash: "a".repeat(64),
  created_at: "2026-07-01T01:02:03",
  row_count: 16000,
  action_row_count: 7090,
  basket_forecast_7d: 1809147.2231469,
  suggestion_units: 731191,
};

function renderInbox(agentId = "retail.replenishment") {
  return render(
    <LanguageProvider>
      <AgentHandoffInbox agentId={agentId} title="Received forecast baskets" />
    </LanguageProvider>,
  );
}

describe("AgentHandoffInbox", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ items: [item], count: 1 }) });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("loads target-agent summaries and displays persisted values", async () => {
    renderInbox();
    expect(await screen.findByText("Received forecast baskets")).toBeInTheDocument();
    expect(screen.getByText("GRC")).toBeInTheDocument();
    expect(screen.getByText("7,090")).toBeInTheDocument();
    expect(screen.getByText("731,191")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toContain("agent=retail.replenishment");
  });

  it("loads the frozen snapshot only on detail and does not recalculate it", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        handoff: {
          ...item,
          source_snapshot_date: "2026-07-01",
          payload: {
            grain: "sku_store",
            row_count: 16000,
            rows: [{ store_id: "S001", sku_id: "SKU-001", suggestion: 25, forecast_7d: 86.1 }],
          },
        },
      }),
    });
    renderInbox();
    const button = await screen.findByRole("button", { name: "Inspect frozen basket" });
    fireEvent.click(button);
    await screen.findByText(/Snapshot 2026-07-01/);
    const detail = screen.getByRole("table");
    expect(within(detail).getByText("SKU-001")).toBeInTheDocument();
    expect(within(detail).getByText("25")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/retail/agent-handoffs/handoff-1");
  });

  it("does not render in fixture mode", async () => {
    render(
      <LanguageProvider>
        <AgentHandoffInbox
          enabled={false}
          agentId="retail.inventory_risk"
          title="Demand Forecasting flags"
        />
      </LanguageProvider>,
    );
    await waitFor(() => expect(screen.queryByText("Demand Forecasting flags")).not.toBeInTheDocument());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
