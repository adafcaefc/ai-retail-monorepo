import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import InventoryRiskDashboard from "./InventoryRiskDashboard.jsx";
import fixture from "./data/fixture.json";

/*
 * No mock of the data gateway. The fixture provider is pure and synchronous,
 * so the dashboard renders against the same numbers a reader would see — which
 * makes these assertions a check on the whole chain, not on a stub.
 *
 * Recharts needs a real box to lay out inside; jsdom reports zero for every
 * element, so ResponsiveContainer would render nothing and the SVG assertions
 * would be vacuous. Pinning the container size is what makes the charts real
 * here.
 */
beforeEach(() => {
  window.localStorage.clear();

  for (const [property, value] of [
    ["offsetWidth", 960],
    ["offsetHeight", 400],
    ["clientWidth", 960],
    ["clientHeight", 400],
  ]) {
    Object.defineProperty(window.HTMLElement.prototype, property, {
      configurable: true,
      value,
    });
  }
});

function renderDashboard() {
  return render(
    <LanguageProvider>
      <InventoryRiskDashboard />
    </LanguageProvider>,
  );
}

/*
 * The skeleton and the loaded board share `data-testid`, deliberately — it is
 * the same board in two states. So waiting on the test id can hand back the
 * skeleton, and an interaction fired against it lands on controls that are
 * about to be replaced. Wait for content only the loaded board renders.
 */
async function renderSettled() {
  const result = renderDashboard();
  await screen.findByText("Inventory risk register");
  return result;
}

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);

describe("InventoryRiskDashboard", () => {
  it("renders six KPIs, both value panels, the dimension row, and the register", async () => {
    renderDashboard();

    await screen.findByTestId("inventory-risk-dashboard");

    expect(document.querySelectorAll(".risk-kpi")).toHaveLength(6);
    expect(screen.getByText("At-risk value by state")).toBeInTheDocument();
    expect(screen.getByText("Inventory value by category")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by category")).toBeInTheDocument();
    expect(screen.getByText("Stockout-risk by store")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by cluster")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by legal entity")).toBeInTheDocument();
    expect(screen.getByText("Expiry timeline")).toBeInTheDocument();
    expect(screen.getByText("Inventory risk register")).toBeInTheDocument();
  });

  it("shows the whole chain's stockout count, matching the workbook total", async () => {
    renderDashboard();

    const expected = fixture.reference_by_vertical.reduce(
      (running, row) => running + row.stockout_risk_skus,
      0,
    );
    const tile = (await screen.findAllByText("Stockout-risk SKUs"))[0];

    expect(
      within(tile.closest(".risk-kpi")).getByText(String(expected)),
    ).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    renderDashboard();

    expect(await screen.findByText(/Workbook data/)).toBeInTheDocument();
    expect(screen.getByText(/not a live ERP position/)).toBeInTheDocument();
  });

  it("carries the gross-versus-chain-net caveat on the board", async () => {
    renderDashboard();

    expect(
      await screen.findByText(/Store and cluster breakdowns are gross/),
    ).toBeInTheDocument();
  });

  it("scopes to one vertical and reports that vertical's workbook numbers", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Legal entity"), {
      target: { value: "GRC" },
    });

    await waitFor(() => {
      const tile = screen
        .getAllByText("Stockout-risk SKUs")[0]
        .closest(".risk-kpi");
      expect(
        within(tile).getByText(String(grocery.stockout_risk_skus)),
      ).toBeInTheDocument();
    });

    // The scope chip names the active vertical, and clearing restores the
    // chain. Scoped to the summary row: "Grocery" also appears in the select
    // options and on the legal-entity chart.
    const summary = document.querySelector(".risk-scope-summary");
    expect(within(summary).getByText(/Grocery/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));

    await waitFor(() => {
      expect(screen.getByText("All retail inventory")).toBeInTheDocument();
    });
  });

  it("filters the register by state", async () => {
    await renderSettled();

    fireEvent.click(screen.getByRole("button", { name: "Stockout" }));

    await waitFor(() => {
      const rows = document.querySelectorAll(".risk-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(row.className).toContain("risk-row--stockout");
      }
    });
  });

  it("submits a SKU search and narrows to the single matching row", async () => {
    await renderSettled();

    // jsdom does not dispatch submit from a submit-button click, so submit the
    // form directly — the same approach the Demand dashboard's test uses.
    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => {
      expect(document.querySelectorAll(".risk-row")).toHaveLength(1);
    });
    // The term also appears in the search box and the scope chip, so assert
    // against the register row itself.
    const row = document.querySelector(".risk-row");
    expect(within(row).getByText("GRC-001")).toBeInTheDocument();
  });

  it("disables the store filter while the per-store dataset is unavailable", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Store")).toBeDisabled();
  });

  it("pages the register rather than rendering all 800 rows at once", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".risk-row")).toHaveLength(50);
    expect(screen.getByText(/Page 1 \/ 16/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ 16/)).toBeInTheDocument();
    });
  });

  it("orders the register worst-state first", async () => {
    await renderSettled();

    const first = document.querySelector(".risk-row");
    expect(first.className).toContain("risk-row--stockout");
  });
});
