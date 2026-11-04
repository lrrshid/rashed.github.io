// The interface language: English (the default) or Arabic, written right to left.
// The choice is kept in this browser (localStorage), so the app opens in the same language next time, the sign-in
// screen included. js/lang-boot.js applies it to <html lang dir> before the first paint; switching reloads the page
// so every module renders again in the new language. Arabic strings live in js/i18n/ar/ (see labels.js).

const STORAGE_KEY = 'cpc.lang';
export const LANGUAGES = ['en', 'ar'];
// Each language's name in its own script: the switch offers the other language by the name its readers know.
export const LANGUAGE_NAMES = { en: 'English', ar: 'العربية' };

function storedLanguage() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.includes(value) ? value : 'en';
  } catch {
    return 'en';
  }
}

const current = storedLanguage();

export function language() {
  return current;
}

// The language the switch offers.
export function otherLanguage() {
  return current === 'ar' ? 'en' : 'ar';
}

export function isRtl() {
  return current === 'ar';
}

// The Intl locale for dates, numbers and sorting. Arabic keeps the Gregorian calendar and Western digits, the same
// digits as ship and defect numbers (DEF-12) and as the paperwork the fleet already uses.
export function locale() {
  return current === 'ar' ? 'ar-AE-u-ca-gregory-nu-latn' : 'en-GB';
}

// +1 in a left-to-right page, -1 in a right-to-left one: multiply horizontal animation offsets by it so a slide
// "in from the side" comes from the reading start in both languages.
export function inlineSign() {
  return isRtl() ? -1 : 1;
}

export function setLanguage(lang) {
  if (!LANGUAGES.includes(lang) || lang === current) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    return; // storage unavailable: the choice could not be kept, so stay in the current language
  }
  window.location.reload();
}

export function applyDocumentLanguage() {
  document.documentElement.lang = current;
  document.documentElement.dir = isRtl() ? 'rtl' : 'ltr';
}
