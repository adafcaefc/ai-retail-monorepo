/*
 * The gateway, and the reconciliation behind it.
 *
 * These used to assert against `mockDashboard.js` — a payload checked against
 * the thing that produced it, which could only ever pass. The comparisons here
 * are against `a1_demand_forecasting`, the workbook's own sheet, carried into
 * the fixture as `reference_by_vertical`.
 *
 * The API branch IS exercised now, at the bottom of this file. It was not, for
 * as long as `DATA_SOURCE` was read at import time and every test ran in
 * "test" mode — and that gap had a cost: `loadDemandForecastingScenario` threw
 * "backend integration is pending" on the branch no test could reach, so Run
 * scenario was broken in the browser and green here. Resetting the module
 * registry under a stubbed MODE is what reaches it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEMAND_AGENT_ID,
  DEFAULT_DEMAND_LEVERS,
  normalizeDemandDashboard,
} from "./contract.js";
import {
  demandForecastingDataSource,
  loadDemandForecastingDashboard,
  loadDemandForecastingScenario,
} from "./dashboardData.js";
import { buildDashboardFromFixture, computeTrending } from "./selectors.js";
import fixture from "./fixture.json";

const apiChartSeries = {
  source: "synthetic.demand_store_sku_104w",
  grain: "sku_store",
  row_count: 16000,
  ...Object.fromEntries(
    Array.from({ length: 52 }, (_, index) => [`actual_w${52 - index}`, index + 1]),
  ),
  ...Object.fromEntries(
    Array.from({ length: 52 }, (_, index) => [`forecast_w${index + 1}`, 100 + index]),
  ),
};
const apiFixture = {
  ...fixture,
  demand_forecast_series: apiChartSeries,
  seasonality_index: {
    value: 103.125,
    average_seas: 1.03125,
    row_count: 16000,
    source: "retail.temp_engine_store.[Seas]",
    grain: "sku_store",
    aggregation: "AVG(Seas) * 100",
  },
};

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);

describe("the Demand Forecasting gateway", () => {
  it("reads the workbook fixture, not an invented dataset", async () => {
    expect(demandForecastingDataSource()).toBe("fixture");

    const dashboard = await loadDemandForecastingDashboard();

    expect(dashboard.agent).toBe(DEMAND_AGENT_ID);
    expect(dashboard.is_mock).toBe(true);
    expect(dashboard.note).toMatch(/typed into the A1 sheet/);
  });

  it("carries the real eight verticals, not the four that were made up", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const ids = dashboard.filter_options.legal_entities.map((row) => row.value);

    expect(ids).toHaveLength(8);
    expect(ids).toContain("GRC");
    expect(ids).toContain("HNB");
    // HBA and HME were invented and do not exist in the dataset.
    expect(ids).not.toContain("HBA");
    expect(ids).not.toContain("HME");
  });

  it("matches the A1 forecast/trend references and derives live below-ROP risk", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const byId = Object.fromEntries(
      dashboard.kpis.map((kpi) => [kpi.id, kpi.value]),
    );

    expect(byId.forecast_next_7d).toBeCloseTo(grocery.forecast_7d, 3);
    // A1's 46 is a pasted historical reference. Current below-ROP exposure
    // is live in the fixture's item rows, matching the A2 inventory-risk
    // calculation used by the dashboard.
    expect(byId.stockout_risk_skus).toBe(
      fixture.items.filter((item) => item.vertical_id === "GRC" && item.is_stockout_risk).length,
    );
    expect(byId.predicted_to_trend).toBe(grocery.trending_skus);
  });

  it("does not mark every SKU in a scoped category as trending", async () => {
    // Regression: `is_trending` used to be a rank+quota allocation sized to
    // the vertical-wide `trending_skus` count. Once scoped to a category
    // (a handful of SKUs, far fewer than that count), the quota always
    // exceeded the row count and every row in the category was marked
    // trending — this is the bug a user reported: every category showed the
    // same "5", because every GRC category happens to hold exactly 5 SKUs.
    const category = fixture.filter_options.categories.find(
      (row) => row.legal_entity_id === "GRC",
    );
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
      category_group: category.value,
    });
    const trending = dashboard.kpis.find(
      (kpi) => kpi.id === "predicted_to_trend",
    ).value;
    const totalInCategory = fixture.items.filter(
      (item) =>
        item.vertical_id === "GRC" && item.category_id === category.value,
    ).length;

    expect(totalInCategory).toBeGreaterThan(0);
    expect(trending).toBeGreaterThan(0);
    expect(trending).toBeLessThan(totalInCategory);
  });

  it("keeps remaining typed constants separate from the live Demand Trend", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const kpi = (id) => dashboard.kpis.find((row) => row.id === id);

    expect(kpi("forecast_accuracy").value).toBeCloseTo(grocery.accuracy_pct, 6);
    // The standalone fixture has no SQL aggregate. It must not fall back to
    // the old workbook reference just because one is present in the fixture.
    expect(kpi("demand_trend").value).toBeNull();
    expect(kpi("demand_trend").comparison_label).toBe("Unavailable");
    expect(kpi("demand_trend").comparison_label).not.toBe("Workbook constant");

    // The tile says where its number came from rather than implying it was
    // calculated. Two of the six are keyed in by hand; the live seasonality
    // card is checked separately on the API path below.
    expect(kpi("forecast_accuracy").comparison_label).toBe("Workbook constant");
    expect(kpi("forecast_next_7d").comparison_label).toBe("Calculated");
    expect(kpi("seasonality_index").comparison_label).toBe("Calculated");
  });

  it("consumes the backend-calculated Trend and keeps it out of workbook blending", () => {
    const liveTrend = {
      trend_pct: 5.5954,
      actual_4w_total: 1000,
      forecast_4w_total: 1055.954,
      row_count: 2000,
      source: "synthetic.demand_store_sku_32w",
      horizon_independent: true,
      sparkline: [10, 11, 12, 13, 14, 15, 16, 17],
    };
    const dashboard = normalizeDemandDashboard(
      buildDashboardFromFixture(
        { ...fixture, demand_trend: liveTrend },
        { legal_entity_id: "GRC" },
      ),
    );
    const kpi = dashboard.kpis.find((row) => row.id === "demand_trend");

    expect(kpi.value).toBeCloseTo(5.5954, 4);
    expect(kpi.comparison_label).toBe("Calculated");
    expect(kpi.sparkline).toEqual([10, 11, 12, 13, 14, 15, 16, 17]);
    expect(dashboard.demand_trend).toMatchObject(liveTrend);
    expect(kpi.value).not.toBe(grocery.trend_pct);
  });

  it.each([
    ["GRC", 5.5954],
    ["S001", 6.1440],
    ["GRC-C01", 5.7945],
    ["GRC-001", 6.0666],
    ["S001 + GRC-C01", 6.4092],
    ["S001 + GRC-001", 3.8397],
  ])("passes the selected %s scope's calculated Trend to the card", (scope, expected) => {
    const dashboard = normalizeDemandDashboard(
      buildDashboardFromFixture(
        {
          ...fixture,
          demand_trend: {
            trend_pct: expected,
            actual_4w_total: 100,
            forecast_4w_total: 100 + expected,
            row_count: 1,
            source: "synthetic.demand_store_sku_32w",
            horizon_independent: true,
            sparkline: [1, 2, 3, 4, 5, 6, 7, 8],
          },
        },
        { sku: scope },
      ),
    );

    expect(dashboard.kpis.find((row) => row.id === "demand_trend").value)
      .toBeCloseTo(expected, 4);
  });

  it("uses the standalone rows for seasonality, not the monthly GMV curve or typed constant", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const kpi = (id) => dashboard.kpis.find((row) => row.id === id);
    const { by_legal_entity, current_month_index } = fixture.seasonality;

    // The checked-in standalone rows carry the v8.5 Seas value, so the
    // scoped SKU average is 1.14 x 100. The monthly profile is chart-only.
    expect(kpi("seasonality_index").value).toBeCloseTo(114, 6);
    expect(kpi("seasonality_index").value).not.toBeCloseTo(
      by_legal_entity.GRC[current_month_index],
      1,
    );
    expect(kpi("seasonality_index").value).toBeCloseTo(grocery.seasonality_idx, 6);
  });

  it("totals the chain to the sum of its verticals", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const expected = fixture.reference_by_vertical.reduce(
      (running, row) => running + row.forecast_7d,
      0,
    );
    const forecast = dashboard.kpis.find((kpi) => kpi.id === "forecast_next_7d");

    expect(forecast.value).toBeCloseTo(expected, 3);
    expect(dashboard.details.total).toBe(800);
  });

  it("keeps the chart's first forecast week reconciled with the Forecast next 7d KPI", async () => {
    // Regression: the chart's period-1 point used to carry the same
    // illustrativeForecastWave() cosmetic wiggle as every later period, so
    // "next week" on the chart could read visibly off the KPI tile and the
    // "Next period" summary stat -- both meant to be the exact same quantity.
    const dashboard = await loadDemandForecastingDashboard();
    const kpi = dashboard.kpis.find((row) => row.id === "forecast_next_7d").value;
    const { points, history_count: historyCount, summary } = dashboard.forecast;
    const [firstForecast, secondForecast, thirdForecast] = points.slice(historyCount, historyCount + 3);

    expect(Math.abs(firstForecast.forecast - kpi) / kpi).toBeLessThan(0.005);
    expect(summary.find((row) => row.id === "next_period").value).toBe(firstForecast.forecast);

    // The illustrative wave still applies from period 2 onward -- the fix
    // only exempts period 1 -- so the line still visibly wiggles rather than
    // reading flat.
    const laterDelta = Math.abs(thirdForecast.forecast - secondForecast.forecast) / secondForecast.forecast;
    expect(laterDelta).toBeGreaterThan(0.01);
  });

  it("emits a forecast series with a widening interval, and an illustrative history", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      horizon_weeks: 8,
      grain: "weekly",
    });
    const { points, history_count: historyCount } = dashboard.forecast;

    // No real sales history exists at any grain, so the leading points are
    // clearly-labeled fabricated placeholders (see FAKE_HISTORY_MULTIPLIERS
    // in selectors.js), not something claiming to be measured.
    expect(historyCount).toBeGreaterThan(0);
    expect(points).toHaveLength(historyCount + 8);

    const history = points.slice(0, historyCount);
    const forecast = points.slice(historyCount);
    expect(history.every((point) => point.actual !== null)).toBe(true);
    // Every history point but the last has no forecast value. The last one
    // (the boundary, right before the forecast starts) repeats its own
    // `actual` as `forecast` too, so the chart draws one continuous line
    // with a style change at the boundary, not a gap.
    expect(history.slice(0, -1).every((point) => point.forecast === null)).toBe(true);
    expect(history.at(-1).forecast).toBe(history.at(-1).actual);
    expect(forecast.every((point) => point.actual === null && point.forecast !== null)).toBe(true);

    const width = (point) => point.confidence_high - point.confidence_low;
    const relative = forecast.map((point) => width(point) / point.forecast);
    // sqrt(h) growth: the band is wider at the far end than the near one.
    expect(relative.at(-1)).toBeGreaterThan(relative[0]);
    // The chain-blended accuracy behind this moved with the v8.5 workbook
    // (the A1 spec's flat "±12%" was read off v8.2's figures), so this reads
    // the fixture's own accuracy_pct rather than re-asserting a stale number.
    const chainAccuracy = fixture.reference_by_vertical.reduce(
      (running, row) => running + row.accuracy_pct * row.forecast_7d,
      0,
    ) / fixture.reference_by_vertical.reduce((running, row) => running + row.forecast_7d, 0);
    expect(relative[0] / 2).toBeCloseTo(fixture.constants.interval_z * (1 - chainAccuracy / 100), 6);
  });

  it("uses the real demand formula for Daily history, not the fabricated multiplier", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      horizon_weeks: 8,
      grain: "daily",
    });
    const { points, history_count: historyCount } = dashboard.forecast;
    const history = points.slice(0, historyCount);

    // Two history points exactly 7 days apart share the same day-of-week
    // and (this close together) the same seasonal month, so under the real
    // ads x DOW x seasonal x trend formula their values should be nearly
    // identical -- only the trend's tiny 7-day compounding separates them.
    // Under FAKE_HISTORY_MULTIPLIERS' scaling they'd differ by whatever
    // arbitrary ratio those two entries happened to have (~5%+ here).
    const weekBefore = history.at(-8);
    const boundary = history.at(-1);
    expect(boundary.actual / weekBefore.actual).toBeCloseTo(1, 2);
  });

  it("keeps the board on the workbook until a lever is moved", async () => {
    const rest = await loadDemandForecastingDashboard({}, DEFAULT_DEMAND_LEVERS);
    expect(rest.simulation.applied).toBe(false);
    expect(rest.simulation.scenario).toEqual(rest.simulation.baseline);
  });

  it("moves what the formulas reach, and nothing else", async () => {
    const dashboard = await loadDemandForecastingDashboard(
      {},
      { ...DEFAULT_DEMAND_LEVERS, demand: 30 },
    );
    const { baseline, scenario } = dashboard.simulation;

    // f01 scales ADS, so the forecast and the reorder zone both move.
    expect(scenario.forecast_next_7d).toBeGreaterThan(baseline.forecast_next_7d);
    expect(scenario.stockout_risk_skus).toBeGreaterThan(baseline.stockout_risk_skus);
    /*
     * Accuracy and trending are typed constants with no lever anywhere near
     * them, and the payload names them so the panel can say so.
     *
     * Accuracy is compared approximately rather than exactly: it is blended
     * across the scope's verticals weighted by forecast, so a scenario that
     * changes volumes changes the weights. The workbook types 92.4 for all
     * eight, so the blend is 92.4 either way and the difference is 1e-13 of
     * floating point, not a lever taking effect.
     */
    expect(scenario.forecast_accuracy_pct).toBeCloseTo(
      baseline.forecast_accuracy_pct,
      9,
    );
    expect(scenario.predicted_to_trend).toBe(baseline.predicted_to_trend);
    expect(dashboard.simulation.unmodelled).toContain("forecast_accuracy_pct");
  });

  it("previews a scenario without applying it to the board", async () => {
    const preview = await loadDemandForecastingScenario(
      {},
      { ...DEFAULT_DEMAND_LEVERS, demand: 20 },
    );
    expect(preview.simulation.applied).toBe(true);
    expect(preview.forecast.points.length).toBeGreaterThan(0);
  });
});

describe("computeTrending", () => {
  it("adds the mockup's +18 uplift bonus for viral SKUs", () => {
    const items = [
      {
        sku_id: "A",
        name: "Viral SKU",
        growth: 1.3,
        is_trending: true,
        signals: ["viral", "growth"],
        ads: 10,
      },
      {
        sku_id: "B",
        name: "Plain SKU",
        growth: 1.3,
        is_trending: true,
        signals: ["growth"],
        ads: 10,
      },
    ];

    const [viral, plain] = computeTrending(items).sort((a, b) =>
      a.sku_id.localeCompare(b.sku_id),
    );

    // uplift = (growth-1)*100, plus 18 when the SKU is viral.
    expect(plain.predicted_uplift_pct).toBeCloseTo(30, 6);
    expect(viral.predicted_uplift_pct).toBeCloseTo(48, 6);
  });
});

describe("dimensions", () => {
  it("reconciles every breakdown to the chain total", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const { dimensions } = dashboard;
    const total = dimensions.chain_total;

    for (const key of ["categories", "stores", "clusters", "legal_entities"]) {
      const summed = dimensions[key].reduce(
        (running, row) => running + row.forecast_units,
        0,
      );
      expect(summed).toBeCloseTo(total, 3);
    }

    expect(dimensions.categories).toHaveLength(160);
    expect(dimensions.stores).toHaveLength(160);
    expect(dimensions.legal_entities).toHaveLength(8);
  });

  it("derives the seasonality curve from the monthly profile", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const { seasonality } = dashboard.dimensions;

    expect(seasonality).toHaveLength(12);
    // `Constants` B6 says the workbook is evaluated at July.
    expect(seasonality[fixture.seasonality.current_month_index].current).toBe(true);
    expect(seasonality.filter((point) => point.current)).toHaveLength(1);

    // Indices average 100 by construction — they are month over series mean.
    const mean =
      seasonality.reduce((running, point) => running + point.index, 0) / 12;
    expect(mean).toBeCloseTo(100, 6);
  });
});

/*
 * The "api" branch, reached by resetting the module registry under a stubbed
 * MODE. `DATA_SOURCE` is evaluated once at import, so the stub has to be in
 * place before the dynamic import — a top-level import would already have
 * bound it to "fixture".
 *
 * `fetch` answers with the fixture itself. That is the point rather than a
 * shortcut: the backend builder returns rows in exactly this shape, and
 * `backend/tests/test_retail_dashboard_builders.py` asserts field by field
 * that it does. So a board driven by this response and a board driven by the
 * file must agree, and anything these tests catch is the gateway's own doing.
 */
describe("the Demand Forecasting gateway in api mode", () => {
  let load;
  let scenario;
  let fetchMock;

  beforeEach(async () => {
    vi.stubEnv("MODE", "production");
    vi.resetModules();
    fetchMock = vi.fn(async () => ({ ok: true, json: async () => apiFixture }));
    vi.stubGlobal("fetch", fetchMock);
    ({
      loadDemandForecastingDashboard: load,
      loadDemandForecastingScenario: scenario,
    } = await import("./dashboardData.js"));
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("asks the dashboard route, and sends only scope as query", async () => {
    await load({ legal_entity_id: "GRC", grain: "weekly", horizon_weeks: 8 });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain(`/api/html/dashboard/${DEMAND_AGENT_ID}`);
    expect(url).toContain("legal_entity_id=GRC");
    // Grain, horizon and paging are how this board draws the rows, not which
    // rows it asks for. Sending them is a 400 from the route's filter guard.
    expect(url).not.toContain("grain");
    expect(url).not.toContain("horizon_weeks");
  });

  it("sends the selected canonical Store id over the existing API contract", async () => {
    const dashboard = await load({ store_id: "S001" });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("store_id=S001");
    expect(url).not.toContain("store=S001");
    expect(dashboard.scope.store_id).toBe("S001");
  });

  it("builds both chart center lines from the API's 104W series", async () => {
    const dashboard = await load({ horizon_weeks: 4, grain: "weekly" });

    expect(dashboard.demand_forecast_series.source)
      .toBe("synthetic.demand_store_sku_104w");
    expect(dashboard.forecast.points.map((point) => point.label))
      .toEqual(["W-4", "W-3", "W-2", "W-1", "W+1", "W+2", "W+3", "W+4"]);
    expect(dashboard.forecast.points.map((point) => point.actual))
      .toEqual([49, 50, 51, 52, null, null, null, null]);
    expect(dashboard.forecast.points.map((point) => point.forecast))
      .toEqual([null, null, null, null, 100, 101, 102, 103]);

    expect(dashboard.confidence.points.slice(0, 12).map((point) => point.actual))
      .toEqual(Array.from({ length: 12 }, (_, index) => 41 + index));
    expect(dashboard.confidence.points.slice(12).map((point) => point.forecast))
      .toEqual([100, 101, 102, 103]);
  });

  it.each([
    [{}, 103.125, 1.03125, 16000],
    [{ legal_entity_id: "GRC" }, 114, 1.14, 2000],
    [{ store_id: "S001" }, 114, 1.14, 100],
    [{ category_group: "GRC-C01" }, 114, 1.14, 100],
    [{ sku: "GRC-001" }, 114, 1.14, 20],
    [{ store_id: "S001", category_group: "GRC-C01" }, 114, 1.14, 5],
    [{ store_id: "S001", sku: "GRC-001" }, 114, 1.14, 1],
  ])(
    "uses the backend Seas aggregate for the %j scope",
    async (query, value, averageSeas, rowCount) => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          ...apiFixture,
          seasonality_index: {
            ...apiFixture.seasonality_index,
            value,
            average_seas: averageSeas,
            row_count: rowCount,
          },
        }),
      });

      const dashboard = await load(query);
      const kpi = dashboard.kpis.find((row) => row.id === "seasonality_index");

      expect(kpi.value).toBe(value);
      expect(kpi.comparison_label).toBe("Calculated");
      expect(dashboard.seasonality_index).toMatchObject({
        value,
        average_seas: averageSeas,
        row_count: rowCount,
        source: "retail.temp_engine_store.[Seas]",
        grain: "sku_store",
        aggregation: "AVG(Seas) * 100",
      });
    },
  );

  it("forwards supported scopes, consumes live Trend, and ignores Horizon for it", async () => {
    const values = {
      "GRC": 5.5954,
      "S001": 6.1440,
      "GRC-C01": 5.7945,
      "GRC-001": 6.0666,
      "S001 + GRC-C01": 6.4092,
      "S001 + GRC-001": 3.8397,
    };
    const sparklineByScope = {
      "GRC": [10, 11, 12, 13, 14, 15, 16, 17],
      "S001": [20, 21, 22, 23, 24, 25, 26, 27],
      "GRC-C01": [30, 31, 32, 33, 34, 35, 36, 37],
      "GRC-001": [40, 41, 42, 43, 44, 45, 46, 47],
      "S001 + GRC-C01": [50, 51, 52, 53, 54, 55, 56, 57],
      "S001 + GRC-001": [60, 61, 62, 63, 64, 65, 66, 67],
    };
    fetchMock.mockImplementation(async (url) => {
      const parsed = new URL(url, "http://localhost");
      const store = parsed.searchParams.get("store_id");
      const category = parsed.searchParams.get("category_group");
      const sku = parsed.searchParams.get("sku");
      const key = store && category
        ? "S001 + GRC-C01"
        : store && sku
          ? "S001 + GRC-001"
          : store || category || sku || "GRC";
      const trend_pct = values[key];
      return {
        ok: true,
        json: async () => ({
          ...apiFixture,
          demand_trend: {
            trend_pct,
            actual_4w_total: 100,
            forecast_4w_total: 100 + trend_pct,
            row_count: 1,
            source: "synthetic.demand_store_sku_32w",
            horizon_independent: true,
            sparkline: sparklineByScope[key],
          },
        }),
      };
    });

    const cases = [
      [{ legal_entity_id: "GRC" }, values.GRC, "GRC"],
      [{ store_id: "S001" }, values.S001, "S001"],
      [{ category_group: "GRC-C01" }, values["GRC-C01"], "GRC-C01"],
      [{ sku: "GRC-001" }, values["GRC-001"], "GRC-001"],
      [
        { store_id: "S001", category_group: "GRC-C01" },
        values["S001 + GRC-C01"],
        "S001 + GRC-C01",
      ],
      [
        { store_id: "S001", sku: "GRC-001" },
        values["S001 + GRC-001"],
        "S001 + GRC-001",
      ],
    ];

    for (const [query, expected, scopeKey] of cases) {
      const dashboard = await load(query);
      const kpi = dashboard.kpis.find((row) => row.id === "demand_trend");
      expect(kpi.value).toBeCloseTo(expected, 4);
      expect(kpi.comparison_label).toBe("Calculated");
      expect(kpi.sparkline).toEqual(sparklineByScope[scopeKey]);
    }

    const horizonValues = [];
    for (const horizon_weeks of [4, 8, 12, 16]) {
      const dashboard = await load({ legal_entity_id: "GRC", horizon_weeks });
      horizonValues.push(dashboard.kpis.find((kpi) => kpi.id === "demand_trend").value);
    }
    expect(horizonValues).toEqual([values.GRC, values.GRC, values.GRC, values.GRC]);
    const requestedUrls = fetchMock.mock.calls.map(([url]) => url);
    expect(requestedUrls.some((url) => url.includes("sku=GRC-001"))).toBe(true);
    expect(requestedUrls.some((url) => url.includes("category_group=GRC-C01"))).toBe(true);
  });

  it("runs a scenario over the API rows instead of refusing", async () => {
    const preview = await scenario(
      { legal_entity_id: "GRC" },
      { ...DEFAULT_DEMAND_LEVERS, demand: 20 },
    );

    expect(preview.agent).toBe(DEMAND_AGENT_ID);
    expect(preview.simulation.scenario_levers.demand).toBe(20);

    const base = await load({ legal_entity_id: "GRC" });
    expect(preview.kpis.find((kpi) => kpi.id === "forecast_next_7d").value)
      .toBeGreaterThan(base.kpis.find((kpi) => kpi.id === "forecast_next_7d").value);
  });
});
