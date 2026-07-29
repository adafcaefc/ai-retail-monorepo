/**
 * EY mark in the app header.
 *
 * Drop the supplied file at `src/assets/ey-logo.png` (`.jpg`, `.webp` and
 * `.svg` also work) and it is picked up automatically. This file is the
 * light-background variant (dark navy "EY" letters, transparent elsewhere),
 * so `img.ey-logo` in styles.css gives it a white chip to stay legible on
 * the app's dark header/sidebar — it is not meant to sit flush. Vite inlines
 * it as a data URI (`assetsInlineLimit` is effectively unlimited), so the
 * single-file production build stays self-contained.
 *
 * Until that file exists the glob resolves to nothing and the traced fallback
 * below renders instead, so the build never breaks on a missing asset.
 */
const logoModules = import.meta.glob(
  "../assets/ey-logo.{png,jpg,jpeg,webp,svg}",
  { eager: true, query: "?url", import: "default" },
);

const EY_LOGO_SRC = Object.values(logoModules)[0] || null;

export default function EyLogo({ className = "", label = "EY" }) {
  const classes = ["ey-logo", className].filter(Boolean).join(" ");

  if (EY_LOGO_SRC) {
    return <img className={classes} src={EY_LOGO_SRC} alt={label} />;
  }

  return <EyLogoFallback className={classes} label={label} />;
}

/** Traced from the brand PNG — beam #FFE600, letters #FFFFFF, fixed fills. */
function EyLogoFallback({ className, label }) {
  return (
    <svg
      className={className}
      viewBox="0 -29 57 60"
      role="img"
      aria-label={label}
      focusable="false"
    >
      <polygon fill="#FFE600" points="0,-7.4 56.7,-27.8 56.7,-14.4 0,-6.5" />

      <g fill="#FFFFFF">
        <path d="M0 0 H26 V6.5 H7 V11.8 H23 V18.2 H7 V23.5 H26 V30 H0 Z" />

        <path d="M28.2 0 H35.7 L38.5 5.43 L41.3 0 H48.8 L42.1 13 V30 H34.9 V13 Z" />
      </g>
    </svg>
  );
}
