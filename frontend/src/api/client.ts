const BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL ?? ""; // empty -> same origin via vite proxy / nginx

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
  }
  const ct = resp.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return resp.json() as Promise<T>;
  return resp.text() as unknown as T;
}

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`;
}

export async function streamText(
  path: string,
  body: unknown,
  onToken: (t: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`${resp.status} ${resp.statusText}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) onToken(decoder.decode(value, { stream: true }));
  }
}
