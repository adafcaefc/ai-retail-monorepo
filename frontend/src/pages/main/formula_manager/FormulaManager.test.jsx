import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createFormula: vi.fn(),
  deleteFormula: vi.fn(),
  evaluateFormula: vi.fn(),
  fetchFormulas: vi.fn(),
  updateFormula: vi.fn(),
  validateFormula: vi.fn(),
}));

vi.mock("../../../api/formulas.js", () => ({
  createFormula: mocks.createFormula,
  deleteFormula: mocks.deleteFormula,
  evaluateFormula: mocks.evaluateFormula,
  fetchFormulas: mocks.fetchFormulas,
  updateFormula: mocks.updateFormula,
  validateFormula: mocks.validateFormula,
}));

// The real worked examples: the card reads them by formula id, so the fixture
// below borrows a real id to exercise the "try this" wiring end to end.
vi.mock("./workedExamples.json", () => ({
  default: {
    "f19-coverage-gap": [
      {
        label: "Store S004 (Grocery 04 - Bandung)",
        address: "Workforce!N9",
        expected: 10,
        values: { required: 42, scheduled: 32 },
        sources: { required: "Workforce!L9", scheduled: "Workforce!M9" },
      },
      {
        label: "Store S011 (Grocery 11 - Batam)",
        address: "Workforce!N16",
        expected: 10,
        values: { required: 49, scheduled: 39 },
        sources: { required: "Workforce!L16", scheduled: "Workforce!M16" },
      },
    ],
  },
}));

import FormulaManager from "./FormulaManager.jsx";

const COVERAGE_GAP = {
  id: "f19-coverage-gap",
  number: 19,
  name: "Coverage gap",
  logic: "MAX(0, required - scheduled)",
  // Grain is what one row of the inputs counts, and it is required: the
  // editor will not save without it. `sheet` is provenance and reads as
  // nothing.
  grain: "store_roster",
  sheet: "Workforce",
  result_type: "number",
  expression: "MAX(0, required - scheduled)",
  parameters: [
    { key: "required", label: "Required workforce", type: "number", default: 42 },
    { key: "scheduled", label: "Scheduled workforce", type: "number", default: 32 },
  ],
};

const ADS = {
  id: "f01-ads-per-store",
  number: 1,
  name: "ADS per store",
  logic: "Base ADS x seasonality",
  grain: "store_sku",
  sheet: "ENGINE_STORE",
  result_type: "number",
  expression: "base_ads * seasonality",
  parameters: [
    { key: "base_ads", label: "Base ADS", type: "number", default: 20.9096 },
    { key: "seasonality", label: "Seasonality index", type: "number", default: 1.14 },
  ],
};

async function renderPage(items = [COVERAGE_GAP, ADS]) {
  mocks.fetchFormulas.mockResolvedValue({ items, count: items.length });
  render(<FormulaManager />);
  await screen.findByText("Coverage gap");
}

describe("Formula Manager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.validateFormula.mockResolvedValue({
      valid: true,
      errors: [],
      referenced: [],
      undeclared: [],
      unused: [],
    });
  });

  it("lists stored formulas with their expression and worked examples", async () => {
    await renderPage();

    expect(screen.getByRole("heading", { level: 2, name: "Formula Manager" }))
      .toBeInTheDocument();
    expect(screen.getByText("MAX(0, required - scheduled)", { selector: "pre" }))
      .toBeInTheDocument();
    expect(screen.getByText("ADS per store")).toBeInTheDocument();

    // Excel addresses deep-link into the Data Source worksheet viewer.
    const address = screen.getByTitle("Open Workforce!N9 in the workbook");
    expect(address.tagName).toBe("A");
    // "!" survives encodeURIComponent untouched; a sheet name like
    // "What-If · Per Agent" is what the encoding is there for.
    expect(address).toHaveAttribute(
      "href",
      "#main.data_source?cell=Workforce!N9",
    );
  });

  it("traces every loaded input back to its workbook cell", async () => {
    await renderPage();

    // The citations belong to the example, so they appear with it.
    expect(
      screen.queryByTitle("Open Workforce!L9 in the workbook"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Store S004 (Grocery 04 - Bandung)"));

    const required = screen.getByTitle("Open Workforce!L9 in the workbook");
    expect(required).toHaveAttribute(
      "href",
      "#main.data_source?cell=Workforce!L9",
    );
    expect(
      screen.getByTitle("Open Workforce!M9 in the workbook"),
    ).toBeInTheDocument();
  });

  it("leaves the validator uncited when no example is loaded", async () => {
    await renderPage();

    fireEvent.click(screen.getAllByRole("button", { name: "Validate" })[0]);

    expect(screen.getByLabelText("Required workforce")).toBeInTheDocument();
    expect(
      screen.queryByTitle("Open Workforce!L9 in the workbook"),
    ).not.toBeInTheDocument();
  });

  it("filters the list by search", async () => {
    await renderPage();

    fireEvent.change(screen.getByLabelText("Search formulas"), {
      target: { value: "coverage" },
    });

    expect(screen.getByText("Coverage gap")).toBeInTheDocument();
    expect(screen.queryByText("ADS per store")).not.toBeInTheDocument();
  });

  it("shows an error when the formulas cannot be loaded", async () => {
    mocks.fetchFormulas.mockRejectedValue(new Error("Backend is down"));
    render(<FormulaManager />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend is down");
  });

  it("opens the validator with each parameter's default", async () => {
    await renderPage();

    fireEvent.click(screen.getAllByRole("button", { name: "Validate" })[0]);

    expect(screen.getByLabelText("Required workforce")).toHaveValue(42);
    expect(screen.getByLabelText("Scheduled workforce")).toHaveValue(32);
  });

  it("prefills the validator from a worked example and compares to the workbook", async () => {
    await renderPage();
    mocks.evaluateFormula.mockResolvedValue({ result: 10 });

    fireEvent.click(screen.getByText("Store S011 (Grocery 11 - Batam)"));

    // Clicking an example opens the validator and loads that example's inputs.
    expect(screen.getByLabelText("Required workforce")).toHaveValue(49);
    expect(screen.getByLabelText("Scheduled workforce")).toHaveValue(39);

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() =>
      expect(screen.getByTestId("formula-result")).toBeInTheDocument(),
    );
    expect(mocks.evaluateFormula).toHaveBeenCalledWith("f19-coverage-gap", {
      required: 49,
      scheduled: 39,
    });
    expect(screen.getByText("Matches workbook")).toBeInTheDocument();
  });

  it("flags a computed result that disagrees with the workbook", async () => {
    await renderPage();
    mocks.evaluateFormula.mockResolvedValue({ result: 3 });

    fireEvent.click(screen.getByText("Store S004 (Grocery 04 - Bandung)"));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText("Differs from workbook")).toBeInTheDocument();
  });

  it("surfaces an evaluation failure", async () => {
    await renderPage();
    mocks.evaluateFormula.mockRejectedValue(new Error("Division by zero."));

    fireEvent.click(screen.getAllByRole("button", { name: "Validate" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Division by zero.");
  });

  it("blocks saving while the expression is invalid", async () => {
    await renderPage();
    mocks.validateFormula.mockResolvedValue({
      valid: false,
      errors: ["Unknown function 'SUM'. Allowed functions: AND, CEILING, IF."],
      referenced: [],
      undeclared: [],
      unused: [],
    });

    fireEvent.click(screen.getByRole("button", { name: "New formula" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Broken" },
    });
    fireEvent.change(screen.getByLabelText("Expression"), {
      target: { value: "SUM(1, 2)" },
    });

    expect(await screen.findByText(/Unknown function/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save formula" })).toBeDisabled();
    expect(mocks.createFormula).not.toHaveBeenCalled();
  });

  it("creates a formula and reloads the list", async () => {
    await renderPage();
    mocks.createFormula.mockResolvedValue({ id: "new-one" });

    fireEvent.click(screen.getByRole("button", { name: "New formula" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Doubled ADS" },
    });
    fireEvent.change(screen.getByLabelText("Expression"), {
      target: { value: "ads * 2" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Add parameter" }));
    fireEvent.change(screen.getByLabelText("Parameter 1 name"), {
      target: { value: "ads" },
    });

    // Grain has no default, so a new formula cannot be saved until its author
    // says what one row of its inputs counts. Assert that before choosing one:
    // the guard is the point of the field.
    expect(screen.getByRole("button", { name: "Save formula" })).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText(/Grain — what one row of the inputs counts/),
      { target: { value: "store_sku" } },
    );

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save formula" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save formula" }));

    await waitFor(() => expect(mocks.createFormula).toHaveBeenCalledTimes(1));
    expect(mocks.createFormula.mock.calls[0][0]).toMatchObject({
      name: "Doubled ADS",
      expression: "ads * 2",
      grain: "store_sku",
      parameters: [{ key: "ads", label: "ads", type: "number" }],
    });
    // The list is refetched so the new row appears.
    expect(mocks.fetchFormulas).toHaveBeenCalledTimes(2);
  });

  it("edits an existing formula through PUT, not POST", async () => {
    await renderPage();
    mocks.updateFormula.mockResolvedValue({ id: COVERAGE_GAP.id });

    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    expect(screen.getByLabelText("Name")).toHaveValue("Coverage gap");

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Coverage shortfall" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save formula" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save formula" }));

    await waitFor(() => expect(mocks.updateFormula).toHaveBeenCalledTimes(1));
    expect(mocks.updateFormula.mock.calls[0][0]).toBe("f19-coverage-gap");
    expect(mocks.createFormula).not.toHaveBeenCalled();
  });

  it("requires a confirmation before deleting", async () => {
    await renderPage();
    mocks.deleteFormula.mockResolvedValue({ deleted: true });

    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(mocks.deleteFormula).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() =>
      expect(mocks.deleteFormula).toHaveBeenCalledWith("f19-coverage-gap"),
    );
    expect(mocks.fetchFormulas).toHaveBeenCalledTimes(2);
  });
});
