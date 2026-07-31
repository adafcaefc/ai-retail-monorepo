/* @react-refresh skip */
// QC-058: which language the board is reading in, and how components ask.
//
// The choice is remembered in localStorage so a reload during a session does
// not drop back to English mid-presentation.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { DEFAULT_LANGUAGE, translate } from "./i18n.js";

const STORAGE_KEY = "ledgerline.language";

const LanguageContext = createContext({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => {},
  t: (text) => text,
});

function readStored() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export function LanguageProvider({ children }) {
  const [language, setLanguage] = useState(readStored);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // A private-mode block must not stop the toggle working for this session.
    }
    document.documentElement.lang = language;
  }, [language]);

  const t = useCallback((text) => translate(text, language), [language]);

  const value = useMemo(
    () => ({ language, setLanguage, t }),
    [language, t]
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
