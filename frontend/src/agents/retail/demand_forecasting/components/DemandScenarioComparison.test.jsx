import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => ({
  CartesianGrid: () => null,
  Legend: () => null,
  Line: () => null,
  LineChart: ({ children }) => <div>{children}</div>,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: ({ domain }) => (
    <output data-testid="scenario-y-axis" data-domain={JSON.stringify(domain)} />
  ),
}));

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import DemandScenarioComparison from "./DemandScenarioComparison.jsx";

const baseline = {
  points: [
    { label: "W+1", forecast: 370000 },
    { label: "W+2", forecast: 400000 },
  ],
};

function scenario(id, values) {
  return {
    id,
    name: id,
    forecast: {
      points: values.map((forecast, index) => ({ label: `W+${index + 1}`, forecast })),
    },
    levers: { demand: 0, promo: 0, markdown: 0, inbound: 0, lead: 0, safety: 0 },
    metrics: { forecast_next_7d: values.reduce((total, value) => total + value, 0) },
    savedAt: "12:00:00",
  };
}

function renderComparison(scenarios) {
  return render(
    <LanguageProvider>
      <DemandScenarioComparison
        baselineForecast={baseline}
        scenarios={scenarios}
        onRemove={vi.fn()}
      />
    </LanguageProvider>,
  );
}

describe("Demand Compare Scenarios chart", () => {
  it("passes a padded domain built from baseline and all visible scenarios", () => {
    renderComparison([
      scenario("Scenario A", [500000, 450000]),
      scenario("Scenario B", [520000, 480000]),
    ]);

    expect(JSON.parse(screen.getByTestId("scenario-y-axis").dataset.domain))
      .toEqual([355000, 535000]);
  });

  it("recalculates the domain when visible scenario data changes", () => {
    const { rerender } = renderComparison([scenario("Scenario A", [500000, 450000])]);

    rerender(
      <LanguageProvider>
        <DemandScenarioComparison
          baselineForecast={baseline}
          scenarios={[scenario("Scenario A", [600000, 590000])]}
          onRemove={vi.fn()}
        />
      </LanguageProvider>,
    );

    expect(JSON.parse(screen.getByTestId("scenario-y-axis").dataset.domain))
      .toEqual([347000, 623000]);
  });
});
