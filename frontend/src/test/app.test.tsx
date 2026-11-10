import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ClaimCard from "../components/ClaimCard";
import { formatBytes, pct, seconds, timeAgo } from "../lib/format";
import type { ClaimResult, Settings } from "../lib/types";
import Dashboard from "../pages/Dashboard";
import Evaluation from "../pages/Evaluation";
import HistoryPage from "../pages/History";
import Landing from "../pages/Landing";
import Library from "../pages/Library";
import NewVerification from "../pages/NewVerification";
import SettingsPage from "../pages/Settings";
import { MODELS_OK, mockApi, renderApp } from "./helpers";

const claim: ClaimResult = {
  id: "C1", text: "The tower is 150 metres tall.", sentence: "It is 150 metres tall.", sentence_id: 2, order: 1, source: "auto",
  resolved_pronoun: false, context_note: "", status: "CONTRADICTED", confidence: 0.94,
  scores: { entailment: 0.02, contradiction: 0.94, neutral: 0.04 }, explanation: "factsheet.txt (page 1) contradicts the claim.",
  conflict: false, needs_review: true, review_reasons: ["low_confidence"], retrieval_seconds: 0.01,
  evidence: [
    { passage_id: 1, doc_id: 1, doc_name: "factsheet.txt", page: 1, text: "The tower is 330 metres tall.", bm25_score: 4.2, bm25_rank: 1, dense_score: 0.81, dense_rank: 1, fused_score: 0.033, rank: 1, nli: { entailment: 0.02, contradiction: 0.94, neutral: 0.04 }, relation: "contradicts", primary: true },
    { passage_id: 2, doc_id: 1, doc_name: "factsheet.txt", page: 2, text: "Other passage text.", bm25_score: null, bm25_rank: null, dense_score: 0.3, dense_rank: 4, fused_score: 0.01, rank: 2, nli: { entailment: 0.1, contradiction: 0.1, neutral: 0.8 }, relation: "neutral" },
  ],
};

const SETTINGS: Settings = {
  nli_model: "cross-encoder/nli-deberta-v3-base", embedding_model: "sentence-transformers/all-MiniLM-L6-v2", embedding_backend: "auto", device: "auto",
  nli_batch_size: 8, chunk_words: 120, chunk_overlap_sentences: 1, top_k: 5, bm25_candidates: 20, dense_candidates: 20, rrf_k: 60,
  bm25_weight: 1, dense_weight: 1, nli_top_k: 5, entail_threshold: 0.7, contradict_threshold: 0.7, margin: 0.1, review_threshold: 0.85,
  near_miss_floor: 0.4, split_compound: true, resolve_pronouns: true, max_claims: 60, theme: "system",
};

describe("format helpers", () => {
  it("formats numbers", () => {
    expect(pct(0.9312, 1)).toBe("93.1%");
    expect(pct(null)).toBe("-");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(seconds(0.25)).toBe("250 ms");
    expect(seconds(3.14)).toBe("3.1 s");
    expect(timeAgo(new Date().toISOString())).toBe("just now");
  });
});

describe("ClaimCard", () => {
  it("expands to show verdict explanation, NLI scores, source and page", () => {
    renderApp(<ClaimCard claim={claim} />);
    expect(screen.getByText("The tower is 150 metres tall.")).toBeInTheDocument();
    expect(screen.getByText("Contradicted")).toBeInTheDocument();
    expect(screen.getByText("Needs human review")).toBeInTheDocument();
    expect(screen.queryByText("Why this verdict")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("Why this verdict")).toBeInTheDocument();
    expect(screen.getByText("The tower is 330 metres tall.")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByText("Contradicts claim")).toBeInTheDocument();
    expect(screen.getByText(/Show 1 additional evidence passage/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Show 1 additional evidence passage/));
    expect(screen.getByText("Other passage text.")).toBeInTheDocument();
  });
});

describe("pages", () => {
  it("landing page has the headline and a working call to action", () => {
    renderApp(<Landing />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Verify");
    expect(screen.getAllByText(/Get started/i)[0].closest("a")).toHaveAttribute("href", "/app/verify");
    expect(screen.getAllByText("How it works").length).toBeGreaterThan(1);
  });

  it("dashboard shows an empty state without verifications", async () => {
    mockApi({ "GET /api/models/status": MODELS_OK, "GET /api/stats/overview": { sessions: 0, completed: 0, documents: 0, passages: 0, claims: { supported: 0, contradicted: 0, insufficient: 0, total_claims: 0, needs_review: 0 }, avg_processing_time: null, recent: [], models: MODELS_OK } });
    renderApp(<Dashboard />);
    expect(await screen.findByText("No claims verified yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("dashboard surfaces backend errors with a retry", async () => {
    mockApi({ "GET /api/models/status": MODELS_OK });
    renderApp(<Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/not found/i);
    expect(screen.getByText("Try again")).toBeInTheDocument();
  });

  it("library empty state offers upload and samples, and loading samples calls the API", async () => {
    const calls = mockApi({
      "GET /api/models/status": MODELS_OK,
      "GET /api/documents": { documents: [], total: 0, index: { state: "empty", passages: 0, documents: 0, built_at: null, build_seconds: null, embedding_backend: null, message: "" } },
      "POST /api/samples/load": { loaded: ["a.txt"], skipped: [] },
    });
    renderApp(<Library />);
    expect(await screen.findByText("Your library is empty")).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Load samples")[0]);
    await waitFor(() => expect(calls.some((c) => c.key === "POST /api/samples/load")).toBe(true));
  });

  it("history shows an empty state", async () => {
    mockApi({ "GET /api/models/status": MODELS_OK, "GET /api/history": { sessions: [], total: 0 } });
    renderApp(<HistoryPage />);
    expect(await screen.findByText("No verifications yet")).toBeInTheDocument();
  });

  it("history lists sessions with open and delete actions", async () => {
    const calls = mockApi({
      "GET /api/models/status": MODELS_OK,
      "GET /api/history": { total: 1, sessions: [{ id: "abc", created_at: new Date().toISOString(), finished_at: null, status: "completed", title: "Eiffel answer", document_ids: [], progress: { stage: "done", done: 1, total: 1 }, summary: { total_claims: 4, supported: 2, contradicted: 1, insufficient: 1, needs_review: 1 }, processing_time: 2.1, error: null, answer_preview: "preview" }] },
      "DELETE /api/history/abc": { deleted: "abc" },
    });
    renderApp(<HistoryPage />);
    expect(await screen.findByText("Eiffel answer")).toBeInTheDocument();
    expect(screen.getByText("Open report").closest("a")).toHaveAttribute("href", "/app/results/abc");
    fireEvent.click(screen.getByLabelText("Delete verification"));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.key === "DELETE /api/history/abc")).toBe(true));
  });

  it("new verification keeps the verify button disabled until there is text and a document", async () => {
    mockApi({
      "GET /api/models/status": MODELS_OK,
      "GET /api/samples": { documents: [], answers: [], note: "" },
      "GET /api/documents": { documents: [{ id: 1, name: "a.txt", ext: ".txt", size_bytes: 10, sha256: "x", page_count: 1, char_count: 10, word_count: 2, passage_count: 1, meta: {}, is_sample: false, uploaded_at: new Date().toISOString() }], total: 1, index: {} },
    });
    renderApp(<NewVerification />);
    const btn = await screen.findByRole("button", { name: /Verify answer/ });
    expect(btn).toBeDisabled();
    await screen.findByText("a.txt");
    fireEvent.change(screen.getByLabelText("AI-generated answer"), { target: { value: "Paris is the capital of France." } });
    await waitFor(() => expect(screen.getByRole("button", { name: /Verify answer/ })).toBeEnabled());
  });

  it("new verification extracts claims for review and lets the user edit them", async () => {
    const calls = mockApi({
      "GET /api/models/status": MODELS_OK, "GET /api/samples": { documents: [], answers: [], note: "" },
      "GET /api/documents": { documents: [], total: 0, index: {} },
      "POST /api/claims/extract": { count: 1, claims: [{ id: "C1", text: "Paris is in France.", sentence: "Paris is in France.", sentence_id: 1, order: 1, source: "auto", resolved_pronoun: false, context_note: "" }] },
    });
    renderApp(<NewVerification />);
    fireEvent.change(await screen.findByLabelText("AI-generated answer"), { target: { value: "Paris is in France." } });
    fireEvent.click(screen.getByRole("button", { name: /Review claims first/ }));
    const input = await screen.findByLabelText("Claim C1");
    fireEvent.change(input, { target: { value: "Paris is the capital of France." } });
    expect((input as HTMLInputElement).value).toBe("Paris is the capital of France.");
    expect(calls.some((c) => c.key === "POST /api/claims/extract")).toBe(true);
    fireEvent.click(screen.getByLabelText("Remove claim C1"));
    expect(screen.queryByLabelText("Claim C1")).not.toBeInTheDocument();
  });

  it("settings loads values and saves changes", async () => {
    const calls = mockApi({
      "GET /api/models/status": MODELS_OK,
      "GET /api/settings": { settings: SETTINGS, choices: { nli: [{ id: SETTINGS.nli_model, label: "DeBERTa base", note: "n" }], embedding: [{ id: SETTINGS.embedding_model, label: "MiniLM" }] } },
      "PUT /api/settings": (init?: RequestInit) => ({ settings: { ...SETTINGS, ...JSON.parse(String(init?.body)) }, models_reloading: false, reindexing: false }),
    });
    renderApp(<SettingsPage />);
    expect(await screen.findByText("Entailment threshold")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saved" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Entailment threshold/), { target: { value: "0.8" } });
    const save = screen.getByRole("button", { name: /Save changes/ });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(calls.some((c) => c.key === "PUT /api/settings" && JSON.parse(c.body!).entail_threshold === 0.8)).toBe(true));
  });

  it("evaluation explains how to get FEVER data when it is missing", async () => {
    mockApi({ "GET /api/models/status": MODELS_OK, "GET /api/evaluation/status": { data: { claims_file: null, wiki_dir: null, data_dir: "/x", ready: false }, running: null, latest: null, setup_hint: "python evaluation/download_fever.py --split paper_dev" } });
    renderApp(<Evaluation />);
    expect(await screen.findByText("No evaluation results yet")).toBeInTheDocument();
    expect(screen.getByText(/download_fever.py/)).toBeInTheDocument();
  });
});
