import { useCallback, useEffect, useState } from "react";

import { fetchSheetList, fetchSheetPage } from "../../../api/excel.js";

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
 */
export default function DataSource() {
  const [sheets, setSheets] = useState([]);
  const [sheetsError, setSheetsError] = useState("");
  const [sheetsLoading, setSheetsLoading] = useState(true);

  const [activeSheet, setActiveSheet] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);

  const [page, setPage] = useState(null);
  const [pageError, setPageError] = useState("");
  const [pageLoading, setPageLoading] = useState(false);

  const [reloadToken, setReloadToken] = useState(0);

  const retry = useCallback(() => {
    setReloadToken((token) => token + 1);
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
        setActiveSheet((current) => current || items[0]?.name || "");
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

  // Reset paging here rather than in an effect, so switching sheets does not
  // first fire a request at the previous sheet's offset.
  const selectSheet = (name) => {
    setActiveSheet(name);
    setOffset(0);
  };

  const changeLimit = (value) => {
    setLimit(value);
    setOffset(0);
  };

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
          />
        </div>
      ) : null}

      {!sheetsError && !pageError ? (
        <div className="data-source-pager">
          <button
            type="button"
            disabled={offset === 0 || pageLoading}
            onClick={() => setOffset(0)}
          >
            First
          </button>
          <button
            type="button"
            disabled={offset === 0 || pageLoading}
            onClick={() => setOffset(Math.max(0, offset - limit))}
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
            onClick={() => setOffset(offset + limit)}
          >
            Next
          </button>
          <button
            type="button"
            disabled={!page?.has_more || pageLoading}
            onClick={() => setOffset(lastOffset)}
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
