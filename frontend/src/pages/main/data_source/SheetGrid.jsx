import { memo, useEffect, useMemo, useRef } from "react";

import { buildMergeIndex, cellStyle } from "./cellStyle.js";

/*
 * One window of a sheet as an HTML table. Pure: it renders exactly what the
 * backend sent and owns no fetching or state.
 *
 * `table-layout: fixed` plus a <colgroup> is what makes the workbook's own
 * column widths bind — without it the browser re-measures every cell and the
 * widths are advisory. The A/B/C row and the row-number column are not in the
 * workbook; under server-side pagination they are the only thing telling you
 * that you are looking at row 8,001 rather than row 1.
 *
 * `focus` is a deep-linked cell ({ row, column }, both 1-based). It is marked
 * and scrolled to once, and is null for ordinary browsing — a grid that jumped
 * on every page change would be unusable.
 */
function SheetGrid({ columns, rows, merges, columnCount, focus }) {
  const { covered, anchors } = useMemo(
    () => buildMergeIndex(merges),
    [merges]
  );

  const focused = useRef(null);

  useEffect(() => {
    const cell = focused.current;

    // jsdom has no layout, so it ships no scrollIntoView.
    if (focus && cell && typeof cell.scrollIntoView === "function") {
      cell.scrollIntoView({ block: "center", inline: "center" });
    }
  }, [focus, rows]);

  return (
    <table className="xl-sheet">
      <colgroup>
        <col className="xl-rowhead-col" />
        {columns.map((column) => (
          <col key={column.index} style={{ width: `${column.width_px}px` }} />
        ))}
      </colgroup>

      <thead className="xl-head">
        <tr>
          <th className="xl-corner" scope="col" aria-label="Row" />
          {columns.map((column) => (
            <th key={column.index} scope="col">
              {column.letter}
            </th>
          ))}
        </tr>
      </thead>

      <tbody>
        {rows.map((row) => (
          <tr key={row.row}>
            <th className="xl-rowhead" scope="row">
              {row.row}
            </th>
            {renderRow(row, columnCount, covered, anchors, focus, focused)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Whether the cell rendered at this position holds the focused address. */
function holdsFocus(row, column, merge, focus) {
  if (!focus) {
    return false;
  }

  // A merged anchor stands in for every position its span swallows, so the
  // focus can be inside the span rather than on the anchor itself.
  const rowspan = merge?.rowspan || 1;
  const colspan = merge?.colspan || 1;

  return (
    focus.row >= row &&
    focus.row < row + rowspan &&
    focus.column >= column &&
    focus.column < column + colspan
  );
}

function renderRow(row, columnCount, covered, anchors, focus, focused) {
  const cells = [];

  for (let column = 1; column <= columnCount; column += 1) {
    const key = `${row.row}:${column}`;

    // A position swallowed by a span above or to the left emits nothing;
    // the anchor's colSpan/rowSpan already occupies it.
    if (covered.has(key)) {
      continue;
    }

    const merge = anchors.get(key);
    const cell = merge?.clipped
      ? merge.anchor || null
      : row.cells[column - 1] || null;

    const isFocus = holdsFocus(row.row, column, merge, focus);

    const className = [
      cell?.t === "n" && !cell?.a ? "is-number" : "",
      cell?.w ? "is-wrap" : "",
      isFocus ? "is-focus" : ""
    ]
      .filter(Boolean)
      .join(" ");

    cells.push(
      <td
        key={key}
        ref={isFocus ? focused : undefined}
        className={className || undefined}
        style={cellStyle(cell)}
        colSpan={merge && merge.colspan > 1 ? merge.colspan : undefined}
        rowSpan={merge && merge.rowspan > 1 ? merge.rowspan : undefined}
        aria-current={isFocus ? "location" : undefined}
      >
        {cell?.v || ""}
      </td>
    );
  }

  return cells;
}

export default memo(SheetGrid);
