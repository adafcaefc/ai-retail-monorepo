import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSheetList, fetchSheetPage } from "../../../api/excel.js";
import { parseAddress } from "../../excelAddress.js";

import SheetGrid from "./SheetGrid.jsx";

const ROWS_PER_PAGE = [50, 100, 250, 500];
const DEFAULT_LIMIT = 100;

/*
 * Read-only viewer for the workbook in resources/, one sheet and one window of
 * rows at a time.
 *
 * This is the one static page that needs the backend, which is also why it
 * sets `order: 1` in index.js — the first page is the app's default screen,
 * and the default screen has to render during an API outage.
 *
 * A cold backend spends up to ~13s parsing the workbook, so a pending page
 * keeps the previous grid mounted and dimmed rather than blanking: an empty
 * box for 13 seconds reads as broken.
 *
 * `pageTarget` is a deep link from elsewhere in the app -- the Formula
 * Manager's cell citations arrive here as `#main.data_source?cell=Stores!E6`.
 * It selects the sheet, pages to the window holding that row and highlights
 * the cell.
 */
export default function DataSource({ pageTarget }) {
  const [sheets, setSheets] = useState([]);
  const [sheetsError, setSheetsError] = useState("");
  const [sheetsLoading, setSheetsLoading] = useState(true);

  const [activeSheet, setActiveSheet] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);

  // The deep-linked cell, once it has been resolved against the sheet list.
  const [focus, setFocus] = useState(null);
  const [targetError, setTargetError] = useState("");

  const [page, setPage] = useState(null);
  const [pageError, setPageError] = useState("");
  const [pageLoading, setPageLoading] = useState(false);

  const [reloadToken, setReloadToken] = useState(0);

  const requested = pageTarget?.address || "";

  // Read by the sheet-list loader, which must not re-run when either changes:
  // refetching every sheet's dimensions because a citation was clicked, or
  // because the page size changed, would be absurd.
  const wanted = useRef(requested);
  const rowsPerPage = useRef(limit);
  wanted.current = requested;
  rowsPerPage.current = limit;

  // Which address the view is already showing. Without it, every paging change
  // would re-apply the target and yank the view back to the linked cell.
  const applied = useRef("");

  const retry = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  /**
   * Point the view at a deep-linked cell, given the sheets that exist. Returns
   * false when the workbook has no such cell, so the caller can fall back.
   */
  const showCell = useCallback((address, items, perPage) => {
    applied.current = address;

    const cell = parseAddress(address);

    if (!cell || !items.some((sheet) => sheet.name === cell.sheet)) {
      setTargetError(`This workbook has no cell ${address}.`);
      return false;
    }

    setTargetError("");
    setActiveSheet(cell.sheet);
    setOffset(Math.floor((cell.row - 1) / perPage) * perPage);
    setFocus({
      sheet: cell.sheet,
      row: cell.row,
      column: cell.column,
      address
    });

    return true;
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setSheetsLoading(true);
      try {
        const payload = await fetchSheetList();
        if (cancelled) {
          return;
        }
        const items = payload.sheets || [];
        setSheets(items);
        setSheetsError("");

        // A deep link that arrived before the list did picks the sheet *and*
        // its page in this same batch, so the grid never reads a window
        // nobody asked for on the way to the linked cell.
        if (
          !wanted.current ||
          !showCell(wanted.current, items, rowsPerPage.current)
        ) {
          setActiveSheet((current) => current || items[0]?.name || "");
        }
      } catch (loadError) {
        if (!cancelled) {
          setSheetsError(
            loadError.message || "Could not load the workbook."
          );
        }
      } finally {
        if (!cancelled) {
          setSheetsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  useEffect(() => {
    if (!activeSheet) {
      return undefined;
    }

    let cancelled = false;

    (async () => {
      setPageLoading(true);
      try {
        const payload = await fetchSheetPage(activeSheet, { offset, limit });
        // Guards against a slow ENGINE_STORE response landing after the user
        // has already moved to another sheet.
        if (cancelled) {
          return;
        }
        setPage(payload);
        setPageError("");
      } catch (loadError) {
        if (!cancelled) {
          setPage(null);
          setPageError(
            loadError.message || "Could not load this sheet."
          );
        }
      } finally {
        if (!cancelled) {
          setPageLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeSheet, offset, limit, reloadToken]);

  // A citation clicked while this page is already open. The first load is
  // handled above, in the same batch as the sheet list.
  useEffect(() => {
    if (!requested) {
      applied.current = "";
      setTargetError("");
      return;
    }

    if (!sheets.length || applied.current === requested) {
      return;
    }

    showCell(requested, sheets, limit);
  }, [requested, sheets, limit, showCell]);

  // Reset paging here rather than in an effect, so switching sheets does not
  // first fire a request at the previous sheet's offset.
  const selectSheet = (name) => {
    setActiveSheet(name);
    setOffset(0);
    clearFocus();
  };

  const changeLimit = (value) => {
    setLimit(value);
    setOffset(0);
    clearFocus();
  };

  // Paging or switching sheets by hand ends the deep link: the highlight would
  // otherwise sit on a cell the user has navigated away from.
  const goToOffset = (value) => {
    setOffset(value);
    clearFocus();
  };

  function clearFocus() {
    setFocus(null);
    setTargetError("");
  }

  const rowCount = page?.row_count ?? 0;
  const returned = page?.returned_rows ?? 0;
  const lastOffset = rowCount ? Math.floor((rowCount - 1) / limit) * limit : 0;

  return (
    <section
      className="static-page data-source"
      data-testid="data-source"
      aria-label="Data Source"
    >
      <div className="data-source-toolbar">
        <label className="data-source-picker">
          <span>Sheet</span>
          <select
            value={activeSheet}
            disabled={sheetsLoading || !sheets.length}
            onChange={(event) => selectSheet(event.target.value)}
          >
            {sheets.map((sheet) => (
              <option key={sheet.name} value={sheet.name}>
                {`${sheet.name} — ${sheet.row_count.toLocaleString()} × ${sheet.column_count}`}
              </option>
            ))}
          </select>
        </label>

        {sheetsLoading && !sheets.length ? (
          <span className="data-source-status">Loading workbook…</span>
        ) : null}

        {page ? (
          <span className="data-source-status">
            Read-only view of {page.sheet}
          </span>
        ) : null}

        {focus ? (
          <span className="data-source-focus">Showing {focus.address}</span>
        ) : null}

        {targetError ? (
          <span className="data-source-status" role="status">
            {targetError}
          </span>
        ) : null}
      </div>

      {sheetsError ? (
        <p className="data-source-error" role="alert">
          {sheetsError}{" "}
          <button type="button" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}

      {pageError ? (
        <p className="data-source-error" role="alert">
          {pageError}{" "}
          <button type="button" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}

      {!pageError && page && rowCount === 0 ? (
        <p className="data-source-status">This sheet has no rows.</p>
      ) : null}

      {!pageError && page && rowCount > 0 ? (
        <div
          className={`data-source-grid${pageLoading ? " is-loading" : ""}`}
          aria-busy={pageLoading}
        >
          <SheetGrid
            columns={page.columns}
            rows={page.rows}
            merges={page.merges}
            columnCount={page.column_count}
            // Not while the previous sheet's grid is still on screen: the
            // row and column would land on whatever happens to be there.
            focus={focus && focus.sheet === page.sheet ? focus : null}
          />
        </div>
      ) : null}

      {!sheetsError && !pageError ? (
        <div className="data-source-pager">
          <button
            type="button"
            disabled={offset === 0 || pageLoading}
            onClick={() => goToOffset(0)}
          >
            First
          </button>
          <button
            type="button"
            disabled={offset === 0 || pageLoading}
            onClick={() => goToOffset(Math.max(0, offset - limit))}
          >
            Prev
          </button>

          <span className="data-source-status">
            {returned
              ? `Rows ${(offset + 1).toLocaleString()}–${(
                  offset + returned
                ).toLocaleString()} of ${rowCount.toLocaleString()}`
              : "No rows"}
          </span>

          <button
            type="button"
            disabled={!page?.has_more || pageLoading}
            onClick={() => goToOffset(offset + limit)}
          >
            Next
          </button>
          <button
            type="button"
            disabled={!page?.has_more || pageLoading}
            onClick={() => goToOffset(lastOffset)}
          >
            Last
          </button>

          <label className="data-source-picker">
            <span>Rows</span>
            <select
              value={limit}
              onChange={(event) => changeLimit(Number(event.target.value))}
            >
              {ROWS_PER_PAGE.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
    </section>
  );
}
