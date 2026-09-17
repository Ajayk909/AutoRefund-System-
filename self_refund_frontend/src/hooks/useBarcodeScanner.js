import { useEffect, useRef } from "react";

/**
 * USB barcode scanners in their default "HID keyboard" mode type the code
 * very quickly and finish with Enter. This hook listens for such bursts
 * anywhere on the page, so a scan still works when the text box does not
 * have focus (e.g. the customer touched the screen elsewhere).
 *
 * Keystrokes typed into an input/textarea are ignored here; the input's own
 * onChange/Enter handling already covers that case.
 */
export default function useBarcodeScanner(onScan, { enabled = true, minLength = 3, maxGapMs = 60 } = {}) {
  const buffer = useRef("");
  const lastTime = useRef(0);
  const callback = useRef(onScan);

  useEffect(() => {
    callback.current = onScan;
  }, [onScan]);

  useEffect(() => {
    if (!enabled) return undefined;

    const handler = (e) => {
      const target = e.target;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.ctrlKey || e.altKey || e.metaKey) return;

      const now = Date.now();
      if (now - lastTime.current > maxGapMs) buffer.current = "";
      lastTime.current = now;

      if (e.key === "Enter" || e.key === "Tab") {
        const code = buffer.current.trim();
        buffer.current = "";
        if (code.length >= minLength) {
          e.preventDefault();
          callback.current(code);
        }
        return;
      }
      if (e.key.length === 1) buffer.current += e.key;
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [enabled, minLength, maxGapMs]);
}
