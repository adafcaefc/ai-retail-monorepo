import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import ForecastDetailTable from "./ForecastDetailTable.jsx";

const DETAILS = {
  total: 3,
  rows: [
    {
      sku_id: "SKU-271",
      sku_name: "Item 271",
      category_label: "Zebra",
      ads_units_per_day: 271.9,
      forecast_units: 1903,
      forecast_7d_units: 2018,
      trend_pct: 14,
      signals: ["promo"],
      supply_state: "Low",
    },
    {
      sku_id: "SKU-268",
      sku_name: "Item 268",
      category_label: "Bakery",
      ads_units_per_day: 268.6,
      forecast_units: 1880,
      forecast_7d_units: 1990,
      trend_pct: -8.9,
      signals: ["growth"],
      supply_state: "Healthy",
    },
    {
      sku_id: "SKU-265",
      sku_name: "Item 265",
      category_label: "bakery",
      ads_units_per_day: 265.3,
      forecast_units: 1857,
      forecast_7d_units: 1961,
      trend_pct: 30.9,
      signals: ["growth", "promo"],
      supply_state: "Expiry",
    },
  ],
};

function renderTable({ onAskInsight } = {}) {
  return render(
    <LanguageProvider>
      <ForecastDetailTable details={DETAILS} grain="weekly" onSelect={vi.fn()} onAskInsight={onAskInsight} />
    </LanguageProvider>,
  );
}

function renderedSkuIds() {
  return [...document.querySelectorAll(".demand-detail-scroll tbody tr")].map(
    (row) => row.querySelector(".demand-sku-link span")?.textContent,
  );
}

describe("ForecastDetailTable", () => {
  it("keeps forecast descending as the default and exposes sortable headers", () => {
    renderTable();

    expect(screen.getByText("Sorted by forecast descending · 3 matches")).toBeInTheDocument();
    expect(renderedSkuIds()).toEqual(["SKU-271", "SKU-268", "SKU-265"]);

    const headers = screen.getAllByRole("columnheader");
    expect(headers).toHaveLength(8);
    expect(headers.filter((header) => header.getAttribute("aria-sort") === "none")).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Sort by Weekly Forecast" }).closest("th"))
      .toHaveAttribute("aria-sort", "descending");
    expect(screen.getAllByRole("button", { name: /Sort by/i })).toHaveLength(7);
  });

  it("toggles the active sort and updates the subtitle and indicator", () => {
    renderTable();

    fireEvent.click(screen.getByRole("button", { name: "Sort by ADS" }));
    expect(screen.getByText("Sorted by ADS ascending · 3 matches")).toBeInTheDocument();
    expect(renderedSkuIds()).toEqual(["SKU-265", "SKU-268", "SKU-271"]);
    const adsHeader = screen.getByRole("button", { name: "Sort by ADS" }).closest("th");
    expect(adsHeader).toHaveAttribute("aria-sort", "ascending");
    expect(within(adsHeader).getByText("▲")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sort by ADS" }));
    expect(screen.getByText("Sorted by ADS descending · 3 matches")).toBeInTheDocument();
    expect(renderedSkuIds()).toEqual(["SKU-271", "SKU-268", "SKU-265"]);
    expect(adsHeader).toHaveAttribute("aria-sort", "descending");
    expect(within(adsHeader).getByText("▼")).toBeInTheDocument();
  });

  it("asks AI to explain a row using its displayed fields", () => {
    const onAskInsight = vi.fn();
    renderTable({ onAskInsight });

    const firstRow = document.querySelectorAll(".demand-detail-scroll tbody tr")[0];
    fireEvent.click(within(firstRow).getByRole("button", { name: "Ask AI" }));

    expect(onAskInsight).toHaveBeenCalledTimes(1);
    const { row } = onAskInsight.mock.calls[0][0];
    expect(row.title).toBe("Item 271 (SKU-271)");
    expect(row.fields).toContainEqual({ label: "Category", value: "Zebra" });
    expect(row.fields).toContainEqual({ label: "Supply state", value: "Low" });
  });

  it("keeps the header inside the single scroll viewport for sticky scrolling", () => {
    renderTable();

    const scrollRegion = document.querySelector(".demand-detail-scroll");
    const table = scrollRegion.querySelector("table");
    expect(table.querySelector("thead")).toBeInTheDocument();
    expect(table.querySelector("tbody")).toBeInTheDocument();
    expect(scrollRegion.querySelector("tbody")).not.toHaveAttribute("aria-hidden", "true");
  });
});
