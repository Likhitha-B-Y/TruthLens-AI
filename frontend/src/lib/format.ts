import { CheckCircle2, CircleHelp, XCircle } from "lucide-react";
import type { Status } from "./types";

export const STATUS_META: Record<Status, { label: string; short: string; text: string; bg: string; bar: string; hex: string; Icon: typeof CheckCircle2 }> = {
  SUPPORTED: { label: "Supported", short: "Supported", text: "text-ok", bg: "bg-ok-bg/70", bar: "bg-ok", hex: "#16a34a", Icon: CheckCircle2 },
  CONTRADICTED: { label: "Contradicted", short: "Contradicted", text: "text-bad", bg: "bg-bad-bg/70", bar: "bg-bad", hex: "#dc2626", Icon: XCircle },
  INSUFFICIENT_EVIDENCE: { label: "Insufficient evidence", short: "Insufficient", text: "text-warn", bg: "bg-warn-bg/70", bar: "bg-warn", hex: "#d97706", Icon: CircleHelp },
};

export const REVIEW_REASONS: Record<string, string> = {
  conflicting_evidence: "Trusted sources disagree on this claim.",
  low_confidence: "Confidence is below the review threshold.",
  near_threshold: "Evidence leans one way but stayed under the decision threshold.",
  no_evidence_retrieved: "No evidence was found in the selected documents.",
};

export const STAGE_LABELS: Record<string, string> = {
  queued: "Queued", extracting_claims: "Extracting claims", indexing: "Preparing indexes",
  retrieving_evidence: "Retrieving evidence", verifying_with_nli: "Checking evidence with NLI",
  aggregating: "Aggregating verdicts", done: "Done", starting: "Starting", loading_claims: "Loading FEVER claims",
  reading_wikipedia: "Reading Wikipedia pages", embedding_corpus: "Embedding corpus", retrieving: "Retrieving evidence",
  nli_inference: "Running NLI", evaluating: "Computing metrics",
};

export const pct = (v: number | null | undefined, d = 0) => (v == null ? "-" : `${(v * 100).toFixed(d)}%`);
export const num = (v: number | null | undefined, d = 3) => (v == null ? "-" : v.toFixed(d));

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export const seconds = (s: number | null | undefined) => (s == null ? "-" : s < 1 ? `${Math.round(s * 1000)} ms` : `${s.toFixed(1)} s`);
