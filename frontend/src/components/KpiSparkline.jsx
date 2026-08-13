/**
 * The mini-chart on a KPI tile.
 *
 * ONE SHAPE ACROSS ALL THREE BOARDS
 * A filled area under a line — the look Demand Forecasting already had, now
 * shared, so a reader moving between the three boards sees one chart rather
 * than three dialects of one. Colour comes from the tile's own accent through
 * `currentColor`, so a green card cannot draw a blue line.
 *
 * WHAT THE LINE MEANS, WHICH IS NOT ALWAYS TIME
 * `kind` does not change the drawing; it changes what the chart is claiming,
 * and the tile puts that in its tooltip.
 *
 *   "series"        an ordered progression — the forecast curve, the widening
 *                   prediction band. Movement along it is movement forward.
 *   "distribution"  a histogram over ordered buckets: days of cover, shelf
 *                   life, growth index. The shape says whether the number is
 *                   concentrated or spread. It says nothing about time.
 *
 * That distinction is the whole reason this dataset can carry a chart on every
 * tile at all. Three of A1's six figures are constants typed into the workbook
 * and none of the boards has a date column anywhere, so the mockup filled the
 * gaps from `rng(label.length * 97 + i * 131)` — a seeded random walk that
 * reads as measurement. A distribution needs no history, and is real.
 */
export default function KpiSparkline({ values, kind = "distribution" }) {
  if (!values?.length || values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100;
    // A floor of 22 and a ceiling of 4 keep the stroke inside the box at both
    // ends, where a 2px line would otherwise be clipped in half.
    const y = 22 - ((value - min) / range) * 18;
    return `${x},${y}`;
  });

  return (
    <svg
      className="kpi-spark"
      viewBox="0 0 100 24"
      preserveAspectRatio="none"
      role="img"
      aria-label={kind === "series" ? "Trend" : "Distribution"}
    >
      <polygon points={`0,24 ${points.join(" ")} 100,24`} />
      <polyline points={points.join(" ")} />
    </svg>
  );
}
