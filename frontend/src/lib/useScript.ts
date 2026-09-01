import { useEffect, useState } from "react";

const loaded = new Set<string>();

/** Loads an external <script> once per src, sharing across every component
 * that asks for it (both OAuth SDKs are loaded lazily, only when a client
 * id is configured, to keep the unauthenticated bundle light). */
export function useScript(src: string | null): "idle" | "loading" | "ready" | "error" {
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    src && loaded.has(src) ? "ready" : "idle",
  );

  useEffect(() => {
    if (!src) return;
    if (loaded.has(src)) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => {
      loaded.add(src);
      setStatus("ready");
    };
    script.onerror = () => setStatus("error");
    document.head.appendChild(script);
  }, [src]);

  return status;
}
