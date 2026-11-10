import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { ModelStatusProvider } from "../lib/modelStatus";
import { ThemeProvider } from "../lib/theme";
import { ToastProvider } from "../lib/toast";

type Routes = Record<string, unknown | ((init?: RequestInit) => unknown)>;

/** Replace fetch with a route table keyed by "METHOD /path". Unknown routes return 404. */
export function mockApi(routes: Routes) {
  const calls: { key: string; body?: string }[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input).split("?")[0];
    const key = `${init?.method ?? "GET"} ${url}`;
    calls.push({ key, body: init?.body as string | undefined });
    const hit = routes[key];
    if (hit === undefined) return new Response(JSON.stringify({ detail: "not found" }), { status: 404, headers: { "content-type": "application/json" } });
    const body = typeof hit === "function" ? (hit as (i?: RequestInit) => unknown)(init) : hit;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
  return calls;
}

export const MODELS_OK = {
  ready: true,
  nli: { kind: "nli", state: "ready", model: "m", device: "cpu", message: "Ready.", load_seconds: 1, backend: "transformers" },
  embedding: { kind: "embedding", state: "ready", model: "e", device: "cpu", message: "Ready.", load_seconds: 1, backend: "sentence-transformers" },
};

export function renderApp(ui: ReactElement, path = "/") {
  return render(
    <ThemeProvider><ToastProvider><MemoryRouter initialEntries={[path]}><ModelStatusProvider>{ui}</ModelStatusProvider></MemoryRouter></ToastProvider></ThemeProvider>,
  );
}
