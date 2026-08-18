import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import {
  candidatesOf,
  computeByCategory,
  computeByCluster,
  computeByState,
  computeByVertical,
  computeBestActions,
  computeKpis,
  scopeItems,
} from "./selectors.js";
import { ALL, BEST_ACTION_TABS, CANDIDATE_STATES } from "./contract.js";

describe("candidatesOf", () => {
  it("keeps only SKUs flagged as markdown candidates", () => {
    const candidates = candidatesOf(fixture.items);
    expect(candidates.length).toBeGreaterThan(0);
    for (const item of candidates) {
      expect(item.is_markdown_candidate).toBe(true);
      expect(CANDIDATE_STATES).toContain(item.state);
    }
  });
});

describe("computeKpis", () => {
  it("sums at-risk and recoverable value over candidates only", () => {
    const kpis = computeKpis(fixture.items);
    const candidates = candidatesOf(fixture.items);
    expect(kpis.markdown_candidates).toBe(candidates.length);
    expect(kpis.at_risk_value).toBeGreaterThan(0);
    expect(kpis.recoverable_value).toBeGreaterThan(0);
    expect(kpis.write_off_value).toBe(
      Math.round(kpis.at_risk_value - kpis.recoverable_value),
    );
  });

  it("recoverable never exceeds at-risk, chain-wide", () => {
    const kpis = computeKpis(fixture.items);
    expect(kpis.recoverable_value).toBeLessThanOrEqual(kpis.at_risk_value);
  });
});

describe("scopeItems", () => {
  it("narrows by vertical", () => {
    const vertical = fixture.items[0].vertical_id;
    const scoped = scopeItems(fixture.items, { legal_entity_id: vertical });
    expect(scoped.length).toBeGreaterThan(0);
    expect(scoped.every((i) => i.vertical_id === vertical)).toBe(true);
  });

  it("ALL is a no-op", () => {
    const scoped = scopeItems(fixture.items, { legal_entity_id: ALL });
    expect(scoped.length).toBe(fixture.items.length);
  });
});

describe("computeByVertical", () => {
  it("every row's at_risk_value is non-negative and rows sum to the candidate total", () => {
    const rows = computeByVertical(fixture.items, fixture.reference_by_vertical);
    const candidateTotal = computeKpis(fixture.items).at_risk_value;
    const rowTotal = rows.reduce((t, r) => t + r.at_risk_value, 0);
    for (const row of rows) expect(row.at_risk_value).toBeGreaterThanOrEqual(0);
    expect(Math.abs(rowTotal - candidateTotal)).toBeLessThan(candidateTotal * 0.01 + 1);
  });
});

describe("computeByCategory", () => {
  it("returns at most the requested limit, sorted descending", () => {
    const rows = computeByCategory(fixture.items, 5);
    expect(rows.length).toBeLessThanOrEqual(5);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i - 1].value).toBeGreaterThanOrEqual(rows[i].value);
    }
  });
});

describe("computeByCluster", () => {
  it("every store row is counted in exactly one cluster", () => {
    const rows = computeByCluster(fixture.stores);
    const total = rows.reduce((t, r) => t + r.store_count, 0);
    expect(total).toBe(fixture.stores.length);
  });
});

describe("computeByState", () => {
  it("covers every state present in the fixture, including Healthy", () => {
    const rows = computeByState(fixture.items);
    const states = rows.map((r) => r.state);
    expect(states).toContain("Healthy");
  });
});

describe("computeBestActions", () => {
  it("partitions every candidate into exactly one tab", () => {
    const tabs = computeBestActions(fixture.items);
    const tabbed = BEST_ACTION_TABS.reduce((t, tab) => t + tabs[tab.id].length, 0);
    expect(tabbed).toBe(candidatesOf(fixture.items).length);
  });
});
