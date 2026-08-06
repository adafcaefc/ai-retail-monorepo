import { LANGUAGES } from "../i18n.js";
import { useLanguage } from "../LanguageProvider.jsx";

/**
 * Language is an app-level preference rather than a board tool, but it sits
 * with the header controls so the sidebar's bottom edge belongs to the user
 * block alone.
 *
 * The component renders the segmented control and nothing else — no wrapper,
 * no visible caption. It used to carry a "Language" label, which the header
 * has no width for; `aria-label` on the group carries that meaning instead.
 * Placement is the caller's job: see `.topbar-tools` in AppTopbar.
 */
export default function LanguageToggle() {
  const { language, setLanguage } = useLanguage();

  return (
    /* QC-058 */
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
  );
}
