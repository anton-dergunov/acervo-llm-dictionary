export interface StoredSession {
  baseUrl: string;
  email: string;
  token: string;
  userId: string;
}

const STORAGE_KEY = "acervo.backend.session.v1";

function nativeHandler() {
  return window.webkit?.messageHandlers?.acervo;
}

/** One call to the Mac application, answered with its data or refused with its sentence. */
export async function nativeCall<T>(method: string, payload: unknown = {}): Promise<T> {
  const response = await nativeHandler()!.postMessage({ method, payload }) as { data?: T; error?: string };
  if (response.error) throw new Error(response.error);
  return response.data as T;
}

export function normalizeServerURL(raw: string): string {
  const value = raw.trim().replace(/\/+$/, "");
  let url: URL;
  try { url = new URL(value); } catch { throw new Error("Enter a valid server URL."); }
  const local = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) throw new Error("Use HTTPS except for local development.");
  if (url.username || url.password || url.search || url.hash) throw new Error("Enter only the server base URL.");
  const path = url.pathname.replace(/\/$/, "").replace(/\/api\/acervo\/v\d+$/i, "");
  return url.origin + (path === "/" ? "" : path);
}

export const sessionStore = {
  async load(): Promise<StoredSession | null> {
    if (nativeHandler()) return nativeCall<StoredSession | null>("loadSession");
    const value = localStorage.getItem(STORAGE_KEY);
    if (!value) return null;
    try { return JSON.parse(value) as StoredSession; }
    catch { localStorage.removeItem(STORAGE_KEY); return null; }
  },
  async save(session: StoredSession): Promise<void> {
    if (nativeHandler()) await nativeCall("saveSession", { session });
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  },
  async clear(): Promise<void> {
    if (nativeHandler()) await nativeCall("clearSession");
    else localStorage.removeItem(STORAGE_KEY);
  }
};
