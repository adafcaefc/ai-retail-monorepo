// The board for a Retail agent that exists in the sidebar and nowhere else.
//
// Agents 4-9 of the mockup are navigable but unbuilt (see
// `backend/src/llm/agents/retail/common/placeholder.py`). Without this they
// would fall through to `Workboard`, which fetches the empty payload those
// modules return and draws an empty KPI grid — a board that looks broken
// rather than one that says it is not built yet.
//
// It also names what each agent needs from the ones before it, because that
// dependency is the reason the six cannot be built in parallel.

import { useLanguage } from "../../../LanguageProvider.jsx";

/**
 * Build the placeholder board for one agent.
 *
 * `App` renders `dashboardComponent` with a fixed prop set, so the per-agent
 * copy is closed over here rather than passed in at the call site.
 *
 * @param {object} spec
 * @param {string} spec.mockupPage  the mockup's own page id ("a4", "awf")
 * @param {number} spec.agentNumber its position in the mockup sidebar (1-9)
 * @param {string} spec.summary     one line on what the board will answer
 * @param {string[]} spec.covers    the panels the mockup page carries
 * @param {string[]} spec.needs     what has to exist first, and why
 */
export function createPlaceholderBoard(spec) {
  function PlaceholderBoard({ agentName }) {
    const { t } = useLanguage();

    return (
      <section
        className="static-page placeholder-board"
        data-testid={`placeholder-board-${spec.mockupPage}`}
        aria-label={agentName}
      >
        <header className="placeholder-head">
          <span className="placeholder-badge">
            {t("Agent")} {spec.agentNumber}
          </span>

          <h2>{agentName}</h2>

          <p className="placeholder-summary">{t(spec.summary)}</p>
        </header>

        <p className="placeholder-notice" role="status">
          {t(
            "This agent is a navigation entry only. Its dashboard, chat and monitoring are not built yet, so no figures are shown here — and none are implied."
          )}
        </p>

        <div className="placeholder-columns">
          <article className="placeholder-card">
            <h3>{t("Planned for this board")}</h3>

            <ul>
              {spec.covers.map((item) => (
                <li key={item}>{t(item)}</li>
              ))}
            </ul>

            <p className="placeholder-source">
              {t("From mockup page")} <code>{spec.mockupPage}</code>
            </p>
          </article>

          <article className="placeholder-card">
            <h3>{t("Needs to exist first")}</h3>

            <ul>
              {spec.needs.map((item) => (
                <li key={item}>{t(item)}</li>
              ))}
            </ul>

            <p className="placeholder-source">
              {t(
                "Build order is a dependency, not a preference: this agent reads what those produce."
              )}
            </p>
          </article>
        </div>
      </section>
    );
  }

  return PlaceholderBoard;
}

export default createPlaceholderBoard;
