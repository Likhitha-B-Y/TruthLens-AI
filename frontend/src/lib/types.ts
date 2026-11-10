export type Status = "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE";

export interface NLIScores { entailment: number; contradiction: number; neutral: number }

export interface Evidence {
  passage_id: number; doc_id: number; doc_name: string; page: number; text: string;
  bm25_score: number | null; bm25_rank: number | null; dense_score: number | null; dense_rank: number | null;
  fused_score: number; rank: number; nli: NLIScores; relation: "supports" | "contradicts" | "neutral"; primary?: boolean;
}

export interface ClaimResult {
  id: string; text: string; sentence: string; sentence_id: number; order: number; source: string;
  resolved_pronoun: boolean; context_note: string;
  status: Status; confidence: number; scores: NLIScores; explanation: string; conflict: boolean;
  needs_review: boolean; review_reasons: string[]; evidence: Evidence[]; retrieval_seconds: number;
}

export interface ExtractedClaim {
  id: string; text: string; sentence: string; sentence_id: number; order: number; source: string;
  resolved_pronoun: boolean; context_note: string;
}

export interface Summary {
  total_claims: number; supported: number; contradicted: number; insufficient: number; needs_review: number;
  conflicts: number; verdict: string; overall: string; supported_pct: number; contradicted_pct: number;
  insufficient_pct: number; processing_time?: number; timings?: Record<string, number>;
  documents_used?: { id: number; name: string }[]; nli_pairs?: number;
  models?: { nli: string | null; embedding: string | null; embedding_backend: string | null };
}

export interface Progress { stage: string; done: number; total: number }

export interface Session {
  id: string; created_at: string; finished_at: string | null; status: "queued" | "running" | "completed" | "failed";
  answer_text?: string; answer_preview?: string; title: string | null; document_ids: number[];
  progress: Progress; summary: Partial<Summary>; claims?: ClaimResult[];
  processing_time: number | null; error: string | null;
}

export interface DocumentInfo {
  id: number; name: string; ext: string; size_bytes: number; sha256: string; page_count: number; char_count: number;
  word_count: number; passage_count: number; meta: { title?: string; author?: string; page_note?: string };
  is_sample: boolean; uploaded_at: string;
}

export interface IndexInfo {
  state: string; passages: number; documents: number; built_at: string | null; build_seconds: number | null;
  embedding_backend: string | null; message: string;
}

export interface ModelState {
  kind: string; state: "not_loaded" | "loading" | "ready" | "error" | "fallback"; model: string | null;
  device: string | null; message: string; load_seconds: number | null; backend: string | null;
}
export interface ModelsStatus {
  ready: boolean; nli: ModelState; embedding: ModelState; index?: IndexInfo;
  choices?: { nli: { id: string; label: string; note: string }[]; embedding: { id: string; label: string }[] };
}

export interface Settings {
  nli_model: string; embedding_model: string; embedding_backend: "auto" | "sentence-transformers" | "tfidf-lsa";
  device: "auto" | "cpu" | "cuda"; nli_batch_size: number; chunk_words: number; chunk_overlap_sentences: number;
  top_k: number; bm25_candidates: number; dense_candidates: number; rrf_k: number; bm25_weight: number; dense_weight: number;
  nli_top_k: number; entail_threshold: number; contradict_threshold: number; margin: number; review_threshold: number;
  near_miss_floor: number; split_compound: boolean; resolve_pronouns: boolean; max_claims: number;
  theme: "light" | "dark" | "system";
}

export interface Overview {
  sessions: number; completed: number; documents: number; passages: number;
  claims: { supported: number; contradicted: number; insufficient: number; total_claims: number; needs_review: number };
  avg_processing_time: number | null; recent: Session[]; models: ModelsStatus;
}

export interface SampleAnswer { id: string; title: string; answer: string; expected: { text: string; label: Status }[] }

export interface MethodResult {
  name: string; thresholds: Record<string, number>; tuned_on_calibration: boolean; calibration_macro_f1: number | null;
  metrics: {
    n: number; accuracy: number; macro_f1: number; macro_precision: number; macro_recall: number;
    per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
    confusion_matrix: { labels: string[]; matrix: number[][] };
  };
  abstention: { coverage: number; abstained: number; answered: number; selective_error_rate: number | null;
    abstain_precision: number | null; abstain_recall: number | null };
  citation: { citation_correctness: number | null; answered_with_citation: number; fever_style_score: number };
  timing: { retrieval_s_per_claim: number; nli_s_per_claim: number; total_s_per_claim: number; total_s: number };
}
export interface EvalResults {
  generated_at: string; config: Record<string, number | string>;
  dataset: { sampled_claims: number; all: Record<string, number>; calibration: { n: number; labels: Record<string, number> };
    test: { n: number; labels: Record<string, number> }; corpus: { pages: number; passages: number } };
  models: { nli: string; embedding: string; device: string }; index_seconds: number;
  methods: Record<string, MethodResult>;
  retrieval: Record<string, Record<string, number>>; ks: number[];
  examples: Record<string, string>[]; notes: string[]; total_seconds: number;
}
export interface EvalRun {
  id: string; created_at: string; finished_at: string | null; status: "running" | "completed" | "failed";
  config: Record<string, unknown>; progress: Progress; results: EvalResults | null; error: string | null;
}
export interface EvalStatus {
  data: { claims_file: string | null; wiki_dir: string | null; data_dir: string; ready: boolean };
  running: EvalRun | null; latest: EvalRun | null; setup_hint: string;
}
