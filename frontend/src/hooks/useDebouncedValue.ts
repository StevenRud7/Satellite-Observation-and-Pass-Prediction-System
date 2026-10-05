import { useEffect, useState } from "react";

/**
 * Returns `value`, but only updates after it has stopped changing for
 * `delayMs`. Used to avoid firing an API request on every keystroke in
 * search-as-you-type inputs (place search, satellite name search).
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
