import { useEffect, useRef } from "react";
import { useScript } from "../lib/useScript";

// Minimal shape of the Google Identity Services global we actually use.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

export function GoogleSignInButton({ onIdToken }: { onIdToken: (idToken: string) => void }) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const status = useScript(clientId ? "https://accounts.google.com/gsi/client" : null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (status !== "ready" || !clientId || !containerRef.current || !window.google) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (resp) => onIdToken(resp.credential),
    });
    window.google.accounts.id.renderButton(containerRef.current, {
      theme: "outline",
      size: "large",
      width: 320,
      text: "continue_with",
    });
  }, [status, clientId, onIdToken]);

  if (!clientId) return null;
  return <div ref={containerRef} />;
}
