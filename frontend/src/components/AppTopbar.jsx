import EyLogo from "./EyLogo.jsx";
import { LANGUAGES } from "../i18n.js";
import { useLanguage } from "../LanguageProvider.jsx";

/**
 * The application's single header.
 *
 * One bar carries everything that used to be split across two: the EY mark,
 * the sidebar toggle, the active board's title, and the board toolbar. The
 * brand block keeps the dark EY tone; the rest of the bar stays light so it
 * reads as part of the workspace, not as a second dark strip.
 */
export default function AppTopbar({
  sidebarOpen,
  onToggleSidebar,
  kicker = "",
  title = "",
  children = null,
}) {
  const { language, setLanguage } = useLanguage();
  const toggleLabel = sidebarOpen ? "Hide agent list" : "Show agent list";

  return (
    <header className="app-topbar">
      <div className="topbar-brand">
        <button
          type="button"
          className="topbar-toggle"
          aria-label={toggleLabel}
          aria-expanded={sidebarOpen}
          aria-controls="agent-sidebar"
          title={toggleLabel}
          onClick={onToggleSidebar}
        >
          <span className="topbar-toggle-icon" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </button>

        <EyLogo className="topbar-logo" />
      </div>

      <div className="topbar-main">
        <div className="topbar-heading">
          {kicker ? <span className="header-kicker">{kicker}</span> : null}

          {title ? <h1>{title}</h1> : null}
        </div>

        {children}

        {/* QC-058 */}
        <div
          className="language-toggle"
          role="group"
          aria-label="Language"
          data-testid="language-toggle"
        >
          {LANGUAGES.map((option) => (
            <button
              key={option.id}
              type="button"
              className={"lang-btn" + (language === option.id ? " on" : "")}
              aria-pressed={language === option.id}
              title={option.title}
              onClick={() => setLanguage(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
