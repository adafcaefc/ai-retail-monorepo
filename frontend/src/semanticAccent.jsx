/*
 * Inline semantic accenting for AI answers.
 *
 * Colours are applied by PHRASE, not by bare word, because polarity is
 * context-dependent: "high risk" is bad while "high margin" is good — both
 * contain "high". Matching whole phrases keeps the signal trustworthy for a
 * CFO. The lexicon below is intentionally conservative and easy to tune.
 */

const RULES = [
  [
    "sem-danger",
    [
      "high risk",
      "at risk",
      "overdue",
      "past due",
      "shortfall",
      "below target",
      "below buffer",
      "below the buffer",
      "behind plan",
      "behind target",
      "breach",
      "breached",
      "delinquent",
      "non-compliant",
      "over budget",
      "exceeded budget",
      "fraud",
      "leakage",
      "duplicate payment",
      "duplicate payments",
      "loss",
      "losses",
      "declining",
      "deteriorating",
      "critical",
      "urgent",
      "adverse",
      "unfavorable",
      "unfavourable",
      "downside",
      "low confidence",
      "gap to target",
      "cash shortfall"
    ]
  ],
  [
    "sem-good",
    [
      "on track",
      "above target",
      "at target",
      "on plan",
      "on budget",
      "within buffer",
      "within the buffer",
      "healthy",
      "surplus",
      "improved",
      "improving",
      "recovered",
      "recovery",
      "favorable",
      "favourable",
      "high confidence",
      "outperform",
      "outperforming",
      "ahead of plan",
      "ahead of target",
      "mitigated",
      "resolved",
      "reduced risk"
    ]
  ],
  [
    "sem-warn",
    [
      "moderate",
      "watch closely",
      "monitor",
      "medium confidence",
      "marginal",
      "approaching target",
      "near target",
      "slightly below",
      "slightly above"
    ]
  ]
];

const PHRASE_CLASS = new Map();
for (const [cls, phrases] of RULES) {
  for (const phrase of phrases) {
    PHRASE_CLASS.set(phrase.toLowerCase(), cls);
  }
}

const escapeRe = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Longest phrases first so "below the buffer" wins over "below".
const MATCHER = new RegExp(
  `\\b(${[...PHRASE_CLASS.keys()]
    .sort((a, b) => b.length - a.length)
    .map(escapeRe)
    .join("|")})\\b`,
  "gi"
);

/** Split text into { text, cls } segments where cls marks an accented span. */
function segment(text) {
  const out = [];
  let last = 0;
  let match;

  MATCHER.lastIndex = 0;
  while ((match = MATCHER.exec(text))) {
    if (match.index > last) {
      out.push({ text: text.slice(last, match.index) });
    }
    out.push({
      text: match[0],
      cls: PHRASE_CLASS.get(match[0].toLowerCase())
    });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    out.push({ text: text.slice(last) });
  }

  return out;
}

/** Plain text -> React nodes with accented spans. */
export function accentPlain(text) {
  if (!text) {
    return text;
  }
  const segments = segment(text);
  if (segments.length === 1 && !segments[0].cls) {
    return text;
  }
  return segments.map((seg, index) =>
    seg.cls ? (
      <span key={index} className={seg.cls}>
        {seg.text}
      </span>
    ) : (
      seg.text
    )
  );
}

const SKIP_TAGS = new Set(["A", "CODE", "PRE", "TH", "SCRIPT", "STYLE"]);
const SKIP_CLASS = /confidence-(high|medium|low)|sem-(danger|good|warn)/;

/** Backend HTML string -> same string with accented spans injected in text nodes. */
export function accentHtml(html) {
  if (!html || typeof window === "undefined" || typeof DOMParser === "undefined") {
    return html;
  }

  const doc = new DOMParser().parseFromString(
    `<body>${html}</body>`,
    "text/html"
  );

  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const targets = [];
  let node;

  while ((node = walker.nextNode())) {
    if (!node.nodeValue || !node.nodeValue.trim()) {
      continue;
    }

    let skip = false;
    for (
      let el = node.parentElement;
      el && el !== doc.body;
      el = el.parentElement
    ) {
      if (SKIP_TAGS.has(el.tagName) || SKIP_CLASS.test(el.className || "")) {
        skip = true;
        break;
      }
    }

    if (!skip) {
      targets.push(node);
    }
  }

  for (const textNode of targets) {
    const segments = segment(textNode.nodeValue);
    if (segments.length === 1 && !segments[0].cls) {
      continue;
    }

    const frag = doc.createDocumentFragment();
    for (const seg of segments) {
      if (seg.cls) {
        const span = doc.createElement("span");
        span.className = seg.cls;
        span.textContent = seg.text;
        frag.appendChild(span);
      } else {
        frag.appendChild(doc.createTextNode(seg.text));
      }
    }
    textNode.parentNode.replaceChild(frag, textNode);
  }

  return doc.body.innerHTML;
}
