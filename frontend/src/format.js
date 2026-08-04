/*
 * One number format for the whole application, resolved from the active
 * language.
 *
 * This used to be pinned to "en-US" everywhere, on the theory that a figure's
 * separator convention is metadata about the reader's machine, not about the
 * document — three formatters had each picked a different locale (one
 * hard-coded "en-US", two followed whatever the browser reported), so the
 * same EBITDA read `53,685.2` on a KPI tile and `53.685,2` on the chart under
 * it depending on whose laptop was driving the demo.
 *
 * Pinning fixed that disagreement but traded it for a different one: a reader
 * in the Bahasa Indonesia view was still shown the English digit-grouping
 * convention, where "53,685" reads as fifty-three point-six-eight-five to
 * someone whose own convention uses a comma for the decimal mark — a
 * misreading a Big-4 board pack would not risk. So the separator now follows
 * the same toggle the words already follow. What still does not change is the
 * figure's magnitude: 53,685.5 and 53.685,5 name the same EBITDA, and nothing
 * here ever rescales or re-rounds a value — only which glyph plays which role
 * swaps. The toggle is also the only thing that moves it: this is keyed to
 * `language`, never read from the browser, so which convention a reader sees
 * no longer depends on whose machine is driving the demo.
 */
const NUMBER_LOCALE_BY_LANGUAGE = {
  en: "en-US",
  id: "id-ID",
};

const DEFAULT_NUMBER_LOCALE = NUMBER_LOCALE_BY_LANGUAGE.en;

/** The `Intl`/`toLocaleString` locale tag for the active language. */
export function numberLocale(language) {
  return NUMBER_LOCALE_BY_LANGUAGE[language] || DEFAULT_NUMBER_LOCALE;
}

/*
 * The magnitude suffix is a unit of measure, not prose — "IDR" is an ISO 4217
 * code and "mn"/"juta" is the scale it is quoted in, the same role "kg"
 * plays. Unlike the ISO code, the scale word itself does have a native
 * reading in Indonesian finance reporting ("juta"), so — unlike IDR, unlike
 * "vs", "buffer", "hedge", which this codebase already keeps as loanwords —
 * this one does move with the toggle.
 */
const MILLIONS_SUFFIX_BY_LANGUAGE = {
  en: "mn",
  id: "juta",
};

/** The "mn"/"juta" magnitude word for the active language. */
export function millionsSuffix(language) {
  return MILLIONS_SUFFIX_BY_LANGUAGE[language] || MILLIONS_SUFFIX_BY_LANGUAGE.en;
}

/*
 * A `unit` field off the payload may literally be the magnitude word ("mn")
 * or may carry it inside a longer string ("IDR mn"). Only that one word
 * swaps; "IDR", "USD", "%", "d" pass through untouched.
 */
export function translateUnit(unit, language) {
  if (typeof unit !== "string" || !unit) {
    return unit;
  }
  if (language !== "id") {
    return unit;
  }
  return unit.replace(/\bmn\b/g, MILLIONS_SUFFIX_BY_LANGUAGE.id);
}

/** Format a figure for display, or return an em dash when it is not a number. */
export function formatNumber(
  value,
  language,
  { maximumFractionDigits = 2, minimumFractionDigits } = {},
) {
  const numeric = Number(value);

  if (!Number.isFinite(numeric)) {
    return "—";
  }

  return numeric.toLocaleString(numberLocale(language), {
    maximumFractionDigits,
    ...(minimumFractionDigits === undefined ? {} : { minimumFractionDigits }),
  });
}

/*
 * A KPI's `value_kind` (see `_classify_value` in dashboard_blocks.py) says
 * how to dress the number back up: "percent" appends the sign the backend's
 * `_pct()` used to bake into the string, "days" appends "d", "number" is
 * plain. `digits` is the exact decimal count the backend already rounded to
 * (`_round_half_up`) — re-deriving it from the locale string would risk a
 * different rounding, not just a different separator.
 */
export function formatKpiValue(value, kind, digits, language) {
  const formatted = formatNumber(value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  if (kind === "percent") {
    return `${formatted}%`;
  }
  if (kind === "days") {
    return `${formatted}d`;
  }
  return formatted;
}

/*
 * Fills a delta template's "{v}" placeholder with the reformatted number —
 * see `_extract_delta_number` in dashboard_blocks.py for how the template and
 * number were split apart server-side. The template's words are translated
 * separately, through i18n.js, before this runs.
 */
export function fillDeltaTemplate(template, value, kind, digits, language) {
  if (typeof template !== "string") {
    return template;
  }
  return template.replace(
    "{v}",
    formatKpiValue(value, kind, digits, language),
  );
}
