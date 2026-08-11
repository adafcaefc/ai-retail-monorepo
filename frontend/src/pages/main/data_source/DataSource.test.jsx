import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchSheetList: vi.fn(),
  fetchSheetPage: vi.fn(),
}));

vi.mock("../../../api/excel.js", () => ({
  fetchSheetList: mocks.fetchSheetList,
  fetchSheetPage: mocks.fetchSheetPage,
}));

import DataSource from "./DataSource.jsx";

const SHEET_LIST = {
  workbook: "sample.xlsx",
  count: 2,
  sheets: [
    { index: 0, name: "Stores", row_count: 20, column_count: 6 },
    { index: 1, name: "ENGINE_STORE", row_count: 16003, column_count: 20 },
  ],
};

/** One window of a sheet, shaped exactly like GET /api/excel/sheets/{name}. */
function sheetPage(sheet, { offset = 0, limit = 100, rowCount, columnCount }) {
  const returned = Math.min(limit, rowCount - offset);

  return {
    sheet,
    index: 0,
    offset,
    limit,
    row_count: rowCount,
    column_count: columnCount,
    returned_rows: returned,
    has_more: offset + returned < rowCount,
    columns: Array.from({ length: columnCount }, (_unused, index) => ({
      index: index + 1,
      letter: String.fromCharCode(65 + index),
      width_px: 66,
    })),
    merges: [],
    rows: Array.from({ length: returned }, (_unused, index) => {
      const row = offset + index + 1;
      return {
        row,
        cells: Array.from({ length: columnCount }, (_ignored, column) => ({
          v: `r${row}c${column + 1}`,
        })),
      };
    }),
  };
}

function focusedCell() {
  return document.querySelector("td.is-focus");
}

describe("Data Source deep links", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchSheetList.mockResolvedValue(SHEET_LIST);
    mocks.fetchSheetPage.mockImplementation(async (sheet, { offset, limit }) =>
      sheetPage(sheet, {
        offset,
        limit,
        rowCount: sheet === "Stores" ? 20 : 16003,
        columnCount: sheet === "Stores" ? 6 : 20,
      }),
    );
  });

  it("opens on the first sheet and marks nothing without a target", async () => {
    render(<DataSource pageTarget={null} />);

    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenCalledWith("Stores", {
        offset: 0,
        limit: 100,
      });
    });
    expect(await screen.findByText("r1c1")).toBeInTheDocument();
    expect(focusedCell()).toBeNull();
  });

  it("selects the sheet and highlights the cell a citation names", async () => {
    render(
      <DataSource
        pageTarget={{ pageId: "main.data_source", address: "Stores!E6" }}
      />,
    );

    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("Stores", {
        offset: 0,
        limit: 100,
      });
    });

    // E is the fifth column of row 6.
    await waitFor(() => expect(focusedCell()).not.toBeNull());
    expect(focusedCell()).toHaveTextContent("r6c5");
    expect(focusedCell()).toHaveAttribute("aria-current", "location");
    expect(screen.getByText("Showing Stores!E6")).toBeInTheDocument();
  });

  it("pages to the window holding a row deep in the sheet", async () => {
    render(
      <DataSource
        pageTarget={{
          pageId: "main.data_source",
          address: "ENGINE_STORE!R848",
        }}
      />,
    );

    // floor((848 - 1) / 100) * 100 -- the page the row falls on, not page 1.
    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("ENGINE_STORE", {
        offset: 800,
        limit: 100,
      });
    });

    await waitFor(() => expect(focusedCell()).not.toBeNull());
    expect(focusedCell()).toHaveTextContent("r848c18");

    // Straight to the linked sheet: no request for the default one on the way,
    // which on a cold backend is the expensive one.
    expect(mocks.fetchSheetPage.mock.calls.map(([sheet]) => sheet)).toEqual([
      "ENGINE_STORE",
    ]);
  });

  it("drops the highlight once the user pages by hand", async () => {
    render(
      <DataSource
        pageTarget={{ pageId: "main.data_source", address: "Stores!E6" }}
      />,
    );

    await waitFor(() => expect(focusedCell()).not.toBeNull());

    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "ENGINE_STORE" },
    });

    await waitFor(() => {
      expect(mocks.fetchSheetPage).toHaveBeenLastCalledWith("ENGINE_STORE", {
        offset: 0,
        limit: 100,
      });
    });
    expect(focusedCell()).toBeNull();
  });

  it("says so when the workbook has no such cell, without requesting it", async () => {
    render(
      <DataSource
        pageTarget={{ pageId: "main.data_source", address: "Ghost!A1" }}
      />,
    );

    expect(
      await screen.findByText("This workbook has no cell Ghost!A1."),
    ).toBeInTheDocument();
    expect(focusedCell()).toBeNull();
    expect(mocks.fetchSheetPage).not.toHaveBeenCalledWith(
      "Ghost",
      expect.anything(),
    );
  });
});
