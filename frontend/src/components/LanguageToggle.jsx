import { LANGUAGES } from "../i18n.js";
import { useLanguage } from "../LanguageProvider.jsx";

/**
 * Language is an app-level preference, not a board tool, so it lives in the
 * sidebar footer rather than the header toolbar. It is set once and rarely
 * revisited — keeping it out of the header leaves that row for the controls
 * that act on the board currently open.
 */
export default function LanguageToggle() {
  const { language, setLanguage } = useLanguage();

  return (
    <div className="sidebar-footer">
      <span className="sidebar-footer-label">Language</span>

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
  );
}
