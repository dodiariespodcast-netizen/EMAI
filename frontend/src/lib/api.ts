function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured;
  // A production build with no API URL configured talks to whatever origin
  // served it. That's the single-container deployment: the API serves this
  // bundle, so there's nothing to configure and no CORS to get wrong.
  // The dev server runs on a different port than the API, so it still needs
  // an explicit default.
  if (import.meta.env.DEV) return "http://localhost:8000";
  return window.location.origin;
}

const API_BASE_URL = resolveApiBaseUrl();

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }

  get friendlyMessage(): string {
    if (typeof this.detail === "string") return this.detail;
    if (this.detail && typeof this.detail === "object" && "detail" in this.detail) {
      const d = (this.detail as { detail: unknown }).detail;
      if (typeof d === "string") return d;
    }
    return `Request failed (${this.status})`;
  }
}

let authToken: string | null = null;

/** The auth context calls this whenever the token changes (login, logout,
 * refresh on load) so every request from anywhere in the app picks it up
 * without threading it through every call site. */
export function setAuthToken(token: string | null) {
  authToken = token;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  isForm?: boolean;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (opts.params) {
    for (const [key, value] of Object.entries(opts.params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const headers: Record<string, string> = {};
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let body: BodyInit | undefined;
  if (opts.isForm) {
    body = opts.body as BodyInit;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(url.toString(), { method: opts.method ?? "GET", headers, body });

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await res.json() : await res.text();

  if (!res.ok) {
    throw new ApiError(res.status, payload);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"]) => request<T>(path, { params }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  postForm: <T>(path: string, form: URLSearchParams) =>
    request<T>(path, { method: "POST", body: form, isForm: true }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { API_BASE_URL };
