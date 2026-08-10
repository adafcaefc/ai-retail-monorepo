import { useEffect, useRef } from "react";

/**
 * The app's one dialog shell: click-outside and a close button, with the
 * `alerts-modal-*` styles it grew up in (kept so both callers look identical).
 *
 * `scrollResetKey` scrolls the body back to the top whenever it changes. The
 * primary action is pinned to the bottom, so a step can be advanced from
 * halfway down a long list; without this the next step would open already
 * scrolled past its own heading.
 */
export default function Modal({
  title,
  subtitle,
  icon,
  onClose,
  children,
  wide = false,
  scrollResetKey,
}) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollResetKey === undefined) {
      return;
    }
    scrollRef.current?.scrollTo({ top: 0 });
  }, [scrollResetKey]);

  return (
    <div className="alerts-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={scrollRef}
        className={"alerts-modal" + (wide ? " alerts-modal-wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="alerts-panel-head">
          <div>
            <h2>
              {icon ? (
                <span className="modal-title-icon" aria-hidden="true">
                  {icon}
                </span>
              ) : null}
              {title}
            </h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button
            type="button"
            className="alerts-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
