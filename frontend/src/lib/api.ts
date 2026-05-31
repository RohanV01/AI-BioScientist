import type { RunEvent } from "../types";

// All requests go through the Vite proxy (dev) or same-origin (built SPA).
async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => fetch(`/api${path}`).then((r) => j<T>(r)),
  post: <T>(path: string, body: unknown) =>
    fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<T>(r)),
};

/**
 * Open the live event WebSocket for a run.
 *
 * DESIGN.md guardrail #2: throttle the stream — incoming events are buffered
 * and flushed to the caller in batches every ~180ms so a heavy stdout burst
 * never causes a render per line.
 */
export function openStream(
  runId: string,
  onBatch: (events: RunEvent[]) => void,
  onStatus?: (open: boolean) => void
): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/runs/${runId}/stream`);

  let buf: RunEvent[] = [];
  const flush = () => {
    if (buf.length) {
      const batch = buf;
      buf = [];
      onBatch(batch);
    }
  };
  const timer = window.setInterval(flush, 180);

  ws.onopen = () => onStatus?.(true);
  ws.onmessage = (e) => {
    try {
      buf.push(JSON.parse(e.data) as RunEvent);
    } catch {
      /* ignore malformed frame */
    }
  };
  ws.onclose = () => {
    window.clearInterval(timer);
    flush();
    onStatus?.(false);
  };
  ws.onerror = () => onStatus?.(false);

  return () => {
    window.clearInterval(timer);
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  };
}
