import { useEffect } from "react";
import { useSettings } from "./settings";

/** Runs before paint so the saved theme is applied without a flash. */
export const themeBootScript = `(function(){try{var s=JSON.parse(localStorage.getItem('emostream.settings.v1')||'{}');var t=s.theme||'light';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

export function ThemeSync() {
  const theme = useSettings((s) => s.theme);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  return null;
}
