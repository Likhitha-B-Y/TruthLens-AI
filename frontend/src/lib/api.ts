import type {
  DocumentInfo, EvalRun, EvalStatus, ExtractedClaim, IndexInfo, ModelsStatus, Overview, SampleAnswer, Session, Settings,
} from "./types";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const BASE = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the TruthLens backend. Is it running on port 8000?", 0, "offline");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let code: string | undefined;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg).join("; ");
      code = j.code;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, code);
  }
  if (res.headers.get("content-type")?.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export interface UploadResult {
  results: { filename: string; ok: boolean; duplicate?: boolean; error?: string; document?: DocumentInfo }[];
  uploaded: number;
  failed: number;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  modelsStatus: () => request<ModelsStatus>("/api/models/status"),
  reloadModels: () => request<ModelsStatus>("/api/models/reload", json("POST")),
  overview: () => request<Overview>("/api/stats/overview"),

  documents: (q?: string, ext?: string) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (ext) p.set("ext", ext);
    return request<{ documents: DocumentInfo[]; total: number; index: IndexInfo }>(`/api/documents?${p}`);
  },
  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<UploadResult>("/api/documents", { method: "POST", body: fd });
  },
  deleteDocument: (id: number) => request<{ deleted: number }>(`/api/documents/${id}`, json("DELETE")),
  document: (id: number) =>
    request<DocumentInfo & { passages: { id: number; page: number; text: string }[] }>(`/api/documents/${id}`),
  rebuildIndex: () => request<IndexInfo>("/api/documents/rebuild-index", json("POST")),
  indexStatus: () => request<IndexInfo>("/api/index/status"),

  extractClaims: (answer: string) =>
    request<{ claims: ExtractedClaim[]; count: number }>("/api/claims/extract", json("POST", { answer })),
  verify: (body: { answer: string; claims?: Partial<ExtractedClaim>[]; document_ids?: number[] }) =>
    request<Session>("/api/verify", json("POST", body)),
  session: (id: string) => request<Session>(`/api/history/${id}`),
  history: () => request<{ sessions: Session[]; total: number }>("/api/history"),
  deleteSession: (id: string) => request<{ deleted: string }>(`/api/history/${id}`, json("DELETE")),
  clearHistory: () => request<{ deleted: number }>("/api/history", json("DELETE")),
  downloadReport: (id: string) => request<Blob>(`/api/history/${id}/report.pdf`),

  settings: () => request<{ settings: Settings; choices: ModelsStatus["choices"] }>("/api/settings"),
  saveSettings: (patch: Partial<Settings>) =>
    request<{ settings: Settings; models_reloading: boolean; reindexing: boolean }>("/api/settings", json("PUT", patch)),
  resetSettings: () => request<{ settings: Settings }>("/api/settings/reset", json("POST")),

  samples: () => request<{ documents: string[]; answers: SampleAnswer[]; note: string }>("/api/samples"),
  loadSamples: () => request<{ loaded: string[]; skipped: string[] }>("/api/samples/load", json("POST")),

  evalStatus: () => request<EvalStatus>("/api/evaluation/status"),
  evalRun: (body: Record<string, unknown>) => request<EvalRun>("/api/evaluation/run", json("POST", body)),
  evalRunGet: (id: string) => request<EvalRun>(`/api/evaluation/runs/${id}`),
};
