/*
 * Cell payloads arrive with short keys and every default omitted, because a
 * page is up to 500 rows x 31 columns. The legend lives beside the producer,
 * in backend/src/excel/formatting.py:
 *
 *   v  text   t  "n" for numbers   b  bold   i  italic
 *   a  left|center|right           va top|middle|bottom   w  wrap
 *   fg #RRGGBB font                bg #RRGGBB solid fill
 *
 * Only the colours and the per-cell overrides are inline styles — everything
 * structural (borders, padding, sticky headers) is in styles.css. These
 * values are workbook data, not design, so they cannot live in a stylesheet.
 */
export function cellStyle(cell) {
  if (!cell) {
    return undefined;
  }

  const style = {};

  if (cell.fg) {
    style.color = cell.fg;
  }

  if (cell.bg) {
    style.backgroundColor = cell.bg;
  }

  if (cell.b) {
    style.fontWeight = 600;
  }

  if (cell.i) {
    style.fontStyle = "italic";
  }

  // An explicit alignment always wins; otherwise numbers go right, matching
  // what Excel shows for an unaligned numeric cell.
  if (cell.a) {
    style.textAlign = cell.a;
  }

  if (cell.va) {
    style.verticalAlign = cell.va;
  }

  return Object.keys(style).length ? style : undefined;
}

/**
 * Merged ranges arrive once, at the top level. Expand them into the two
 * lookups the row walk needs: which positions a span swallows, and what to
 * render at each anchor.
 *
 * `clipped` marks a range whose real anchor sits above this page. The backend
 * sends that cell's payload along, so a banner split by pagination still
 * renders its text instead of an empty box.
 */
export function buildMergeIndex(merges) {
  const covered = new Set();
  const anchors = new Map();

  for (const merge of merges || []) {
    const { row, column, rowspan, colspan } = merge;

    anchors.set(`${row}:${column}`, merge);

    for (let r = row; r < row + rowspan; r += 1) {
      for (let c = column; c < column + colspan; c += 1) {
        if (r === row && c === column) {
          continue;
        }
        covered.add(`${r}:${c}`);
      }
    }
  }

  return { covered, anchors };
}
