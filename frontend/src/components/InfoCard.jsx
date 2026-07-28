import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Floating info card, ported from #floatInfo in the v9.4 mockup.
 *
 * Clicking a KPI, chart, table or simulator stat opens this card
 * instead of firing a chat turn. The CFO reads what the element
 * means and only then chooses "Continue in chat".
 *
 * `anchor` is the DOMRect of the clicked element; the card flips
 * above / clamps horizontally so it always stays in the viewport.
 */
export default function InfoCard({
  entry,
  anchor,
  context,
  busy = false,
  onContinue,
  onClose
}) {
  const cardRef = useRef(null);
  const [position, setPosition] = useState(null);

  useLayoutEffect(() => {
    const card = cardRef.current;
    if (!card || !anchor) {
      return;
    }

    const { offsetWidth: width, offsetHeight: height } = card;
    const gap = 8;
    const margin = 8;

    let left = anchor.left;
    if (left + width > window.innerWidth - margin) {
      left = window.innerWidth - width - margin;
    }
    if (left < margin) {
      left = margin;
    }

    let top = anchor.bottom + gap;
    if (top + height > window.innerHeight - margin) {
      top = anchor.top - height - gap;
    }
    if (top < margin) {
      top = margin;
    }

    setPosition({ left, top });
  }, [anchor, entry]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape") {
        onClose?.();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    // The board scrolls and the panel resizes; rather than track the
    // anchor continuously, dismiss so the card never points at nothing.
    function dismiss() {
      onClose?.();
    }

    window.addEventListener("resize", dismiss);
    window.addEventListener("scroll", dismiss, true);
    return () => {
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("scroll", dismiss, true);
    };
  }, [onClose]);

  if (!entry) {
    return null;
  }

  return (
    <>
      <div
        className="info-card-scrim"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={cardRef}
        className="info-card"
        role="dialog"
        aria-label={entry.el}
        data-testid="info-card"
        style={{
          left: position ? `${position.left}px` : "-9999px",
          top: position ? `${position.top}px` : "-9999px",
          visibility: position ? "visible" : "hidden"
        }}
      >
        <div className="info-card-head">
          <span className="info-card-title">{entry.el}</span>
          <button
            type="button"
            className="info-card-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <p className="info-card-text">{entry.x}</p>

        {context ? (
          <div className="info-card-reading">
            <span>Now</span>
            <strong>{context}</strong>
          </div>
        ) : null}

        {entry.f ? (
          <div className="info-card-formula">{entry.f}</div>
        ) : null}

        <button
          type="button"
          className="info-card-cta"
          data-testid="info-card-continue"
          disabled={busy}
          onClick={onContinue}
        >
          {busy ? "Agent is busy…" : "Continue in chat ▶"}
        </button>
      </div>
    </>
  );
}
