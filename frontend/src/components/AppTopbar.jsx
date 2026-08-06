import EyLogo from "./EyLogo.jsx";
import LanguageToggle from "./LanguageToggle.jsx";

/**
 * The application's single header.
 *
 * One bar carries everything that used to be split across two: the EY mark,
 * the sidebar toggle, the active board's title, and the board toolbar. The
 * brand block keeps the dark EY tone; the rest of the bar stays light so it
 * reads as part of the workspace, not as a second dark strip.
 *
 * The board toolbar and the language toggle share one `.topbar-tools` group.
 * That grouping is load-bearing: the free space in this row must be claimed by
 * exactly one `margin-left: auto`. When the toggle sat here as its own flex
 * item it brought a second one, the two split the space between them, and the
 * toolbar never reached the header's right edge.
 */
export default function AppTopbar({
  sidebarOpen,
  onToggleSidebar,
  kicker = "",
  title = "",
  children = null,
}) {
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

        <div className="topbar-tools">
          {children}

          <LanguageToggle />
        </div>
      </div>
    </header>
  );
}
