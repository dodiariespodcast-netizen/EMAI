import { useMemo, useState } from "react";
import { PublicClientApplication } from "@azure/msal-browser";
import { Button } from "./ui";

export function MicrosoftSignInButton({ onIdToken }: { onIdToken: (idToken: string) => void }) {
  const clientId = import.meta.env.VITE_MICROSOFT_CLIENT_ID;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const msal = useMemo(() => {
    if (!clientId) return null;
    return new PublicClientApplication({
      auth: { clientId, authority: "https://login.microsoftonline.com/common", redirectUri: window.location.origin },
    });
  }, [clientId]);

  if (!clientId || !msal) return null;

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      await msal!.initialize();
      const result = await msal!.loginPopup({ scopes: ["openid", "profile", "email"] });
      onIdToken(result.idToken);
    } catch {
      setError("Microsoft sign-in was cancelled or failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button type="button" variant="secondary" className="w-full" disabled={busy} onClick={handleClick}>
        <MicrosoftLogo />
        Continue with Microsoft
      </Button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function MicrosoftLogo() {
  return (
    <svg width="16" height="16" viewBox="0 0 21 21" aria-hidden>
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
