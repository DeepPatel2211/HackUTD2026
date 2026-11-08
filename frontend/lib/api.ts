import type { Dashboard, Investigation, TrendPoint } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* Proxy may return a non-JSON response when the backend is offline. */
    }
    throw new Error(detail);
  }
  return response.json();
}

function query(dataset: string, at?: number | null) {
  const params = new URLSearchParams({ dataset });
  if (at != null) params.set("at", String(at));
  return params;
}
/** Where to reach /api/agents.
 *
 * The Next rewrite proxy buffers server-sent events: every frame of the agent
 * stream arrives together at the end instead of as each agent answers, which
 * throws away the progressive fill the panel is built around. Going straight to
 * the backend keeps the stream live. The proxy path is kept as a fallback so a
 * backend on another host still works, just buffered.
 */
const AGENT_ORIGIN = process.env.NEXT_PUBLIC_AGENT_ORIGIN ?? "http://127.0.0.1:8000";

export function agentStreamUrls(
  dataset: string,
  facilityId: string,
  at: number,
): string[] {
  const params = new URLSearchParams({
    dataset,
    facility_id: facilityId,
    at: String(at),
  });
  const relative = `/api/agents?${params}`;
  return AGENT_ORIGIN ? [`${AGENT_ORIGIN}${relative}`, relative] : [relative];
}

export const api = {
  handoff: (dataset: string, at: number, signal?: AbortSignal) =>
    request<{ now: number; summary: string[]; planned_cost: number; avoided_cost: number; scope: string }>(
      `/api/handoff?${query(dataset, at)}`, { signal }),
  datasets: (signal?: AbortSignal) =>
    request<string[]>("/api/datasets", { signal }),
  dashboard: (dataset: string, at?: number | null, signal?: AbortSignal) =>
    request<Dashboard>(`/api/dashboard?${query(dataset, at)}`, { signal }),
  trend: (
    dataset: string,
    asset: string,
    metric: string,
    at: number,
    signal?: AbortSignal,
  ) => {
    const params = query(dataset, at);
    params.set("asset", asset);
    params.set("metric", metric);
    return request<TrendPoint[]>(`/api/trend?${params}`, { signal });
  },
  investigate: (
    dataset: string,
    facility_id: string,
    at: number,
    signal?: AbortSignal,
  ) =>
    request<Investigation>("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
      body: JSON.stringify({ dataset, facility_id, at }),
    }),
  eventsUrl: (dataset: string, at: number) =>
    `/api/events?${query(dataset, at)}`,
};
