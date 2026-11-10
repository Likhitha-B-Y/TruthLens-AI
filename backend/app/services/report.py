"""PDF verification report (ReportLab)."""
from __future__ import annotations

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from ..config import APP_NAME, APP_VERSION, STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED

PRIMARY = colors.HexColor("#17324D")
SECONDARY = colors.HexColor("#0F766E")
ACCENT = colors.HexColor("#7C3AED")
INK = colors.HexColor("#1E293B")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
PANEL = colors.HexColor("#F8FAFC")
STATUS_COLORS = {
    STATUS_SUPPORTED: (colors.HexColor("#15803D"), colors.HexColor("#DCFCE7"), "SUPPORTED"),
    STATUS_CONTRADICTED: (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2"), "CONTRADICTED"),
    STATUS_INSUFFICIENT: (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7"), "INSUFFICIENT EVIDENCE"),
}
REASON_TEXT = {
    "conflicting_evidence": "Trusted sources disagree on this claim.",
    "low_confidence": "The model's confidence is below the review threshold.",
    "near_threshold": "Evidence leans one way but stayed under the decision threshold.",
    "no_evidence_retrieved": "No evidence was found in the selected documents.",
}

_FONT_CANDIDATES = [
    ("DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique",
     ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"],
     ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"],
     ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf"]),
    ("Arial", "Arial-Bold", "Arial-Italic",
     ["C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"],
     ["C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
     ["C:/Windows/Fonts/ariali.ttf", "/Library/Fonts/Arial Italic.ttf", "/System/Library/Fonts/Supplemental/Arial Italic.ttf"]),
]
_FONTS: dict | None = None


def _fonts() -> dict:
    """Register a Unicode TrueType family if one is available; otherwise use built-in Helvetica."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    for reg, bold, ital, rp, bp, ip in _FONT_CANDIDATES:
        r = next((p for p in rp if os.path.exists(p)), None)
        b = next((p for p in bp if os.path.exists(p)), None)
        i = next((p for p in ip if os.path.exists(p)), None)
        if r and b:
            try:
                pdfmetrics.registerFont(TTFont(reg, r))
                pdfmetrics.registerFont(TTFont(bold, b))
                pdfmetrics.registerFont(TTFont(ital, i or r))
                pdfmetrics.registerFontFamily(reg, normal=reg, bold=bold, italic=ital, boldItalic=bold)
                _FONTS = {"regular": reg, "bold": bold, "italic": ital, "unicode": True}
                return _FONTS
            except Exception:
                continue
    _FONTS = {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique", "unicode": False}
    return _FONTS


def _t(text: str | None) -> str:
    """Escape for ReportLab Paragraph markup and drop characters the font cannot draw."""
    s = escape(text or "")
    if not _fonts()["unicode"]:
        s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    f = _fonts()
    base = dict(fontName=f["regular"], textColor=INK, leading=14, fontSize=9.5, alignment=TA_LEFT)
    return {
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 8, "leading": 11, "textColor": MUTED}),
        "h1": ParagraphStyle("h1", **{**base, "fontName": f["bold"], "fontSize": 17, "leading": 21, "textColor": PRIMARY,
                                       "spaceBefore": 10, "spaceAfter": 6}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": f["bold"], "fontSize": 11.5, "leading": 15, "textColor": PRIMARY,
                                       "spaceBefore": 6, "spaceAfter": 3}),
        "claim": ParagraphStyle("claim", **{**base, "fontName": f["bold"], "fontSize": 10.5, "leading": 14.5}),
        "quote": ParagraphStyle("quote", **{**base, "fontName": f["italic"], "fontSize": 8.8, "leading": 12.5,
                                             "textColor": colors.HexColor("#334155"), "leftIndent": 8}),
        "answer": ParagraphStyle("answer", **{**base, "fontSize": 9.5, "leading": 14, "backColor": PANEL,
                                               "borderPadding": 8, "borderColor": LINE, "borderWidth": 0.6}),
        "warn": ParagraphStyle("warn", **{**base, "fontSize": 8.8, "textColor": colors.HexColor("#92400E")}),
        "title": ParagraphStyle("title", **{**base, "fontName": f["bold"], "fontSize": 24, "leading": 30,
                                             "textColor": PRIMARY}),
        "pill": ParagraphStyle("pill", **{**base, "fontName": f["bold"], "fontSize": 8, "leading": 10,
                                           "textColor": colors.white}),
    }


def _stacked_bar(summary: dict, width: float = 170 * mm, height: float = 14) -> Drawing:
    total = max(summary.get("total_claims", 0), 1)
    d = Drawing(width, height + 14)
    x = 0.0
    for key, name in (("supported", STATUS_SUPPORTED), ("contradicted", STATUS_CONTRADICTED),
                      ("insufficient", STATUS_INSUFFICIENT)):
        w = width * summary.get(key, 0) / total
        if w > 0:
            d.add(Rect(x, 14, w, height, fillColor=STATUS_COLORS[name][0], strokeColor=colors.white, strokeWidth=1))
            x += w
    if summary.get("total_claims", 0) == 0:
        d.add(Rect(0, 14, width, height, fillColor=LINE, strokeColor=colors.white))
    d.add(String(0, 2, "Share of claims: supported / contradicted / insufficient evidence", fontSize=7,
                 fillColor=MUTED, fontName=_fonts()["regular"]))
    return d


def _pill(status: str, st: dict) -> Table:
    fg, _bg, label = STATUS_COLORS.get(status, STATUS_COLORS[STATUS_INSUFFICIENT])
    t = Table([[Paragraph(label, st["pill"])]], colWidths=[46 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fg), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _footer(canvas, doc, session_id: str) -> None:
    canvas.saveState()
    f = _fonts()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont(f["regular"], 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, f"{APP_NAME} - Verification report {session_id}")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _header_band(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, stroke=0, fill=1)
    canvas.setFillColor(SECONDARY)
    canvas.rect(0, A4[1] - 9 * mm, 38 * mm, 9 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont(_fonts()["bold"], 8)
    canvas.drawString(18 * mm, A4[1] - 6 * mm, "TRUTHLENS AI")
    canvas.restoreState()


def build_report(session: dict) -> bytes:
    """Return PDF bytes for a completed verification session."""
    st = _styles()
    f = _fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title=f"{APP_NAME} verification report",
                            author=APP_NAME, subject="Evidence-grounded verification of an AI-generated answer")
    sid = session["id"]
    summary = session.get("summary") or {}
    claims = session.get("claims") or []
    story: list = []
    width = A4[0] - 36 * mm

    # --- title block -------------------------------------------------------------------
    title_tbl = Table([[Paragraph("TruthLens AI", st["title"])],
                       [Paragraph("Evidence-grounded verification report", st["h2"])]], colWidths=[width])
    title_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story += [title_tbl, Spacer(1, 4)]
    try:
        created = datetime.fromisoformat(session["created_at"]).strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        created = session.get("created_at", "")
    docs = ", ".join(d["name"] for d in summary.get("documents_used", [])) or "n/a"
    models = summary.get("models", {})
    meta_rows = [
        ["Session ID", sid], ["Generated", created],
        ["Processing time", f'{summary.get("processing_time", session.get("processing_time", 0)):.1f} s'],
        ["Reference documents", docs],
        ["NLI model", models.get("nli") or "n/a"],
        ["Embedding model", f'{models.get("embedding") or "n/a"} ({models.get("embedding_backend") or "n/a"})'],
    ]
    meta = Table([[Paragraph(f"<b>{_t(k)}</b>", st["small"]), Paragraph(_t(str(v)), st["small"])] for k, v in meta_rows],
                 colWidths=[38 * mm, width - 38 * mm])
    meta.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 10)]

    # --- summary ---------------------------------------------------------------------------
    story.append(Paragraph("1. Verification summary", st["h1"]))
    story.append(Paragraph(_t(summary.get("overall", "No summary available.")), st["body"]))
    story.append(Spacer(1, 8))
    cells = []
    for label, key, name in (("Total claims", "total_claims", None), ("Supported", "supported", STATUS_SUPPORTED),
                             ("Contradicted", "contradicted", STATUS_CONTRADICTED),
                             ("Insufficient", "insufficient", STATUS_INSUFFICIENT),
                             ("Needs review", "needs_review", None)):
        col = STATUS_COLORS[name][0] if name else (ACCENT if key == "needs_review" else PRIMARY)
        cells.append([Paragraph(f'<font size="20" color="{col.hexval().replace("0x", "#")}"><b>{summary.get(key, 0)}</b></font>',
                                st["body"]), Paragraph(label, st["small"])])
    kpi = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[width / 5] * 5)
    kpi.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                             ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("TOPPADDING", (0, 0), (-1, -1), 5),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [kpi, Spacer(1, 8), _stacked_bar(summary, width), Spacer(1, 6)]

    # --- original answer -----------------------------------------------------------------
    story.append(Paragraph("2. Original AI-generated answer", st["h1"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(_t(session.get("answer_text", "")), st["answer"]))
    story.append(Spacer(1, 6))

    # --- claims ------------------------------------------------------------------------------
    story.append(Paragraph("3. Claim-by-claim verification", st["h1"]))
    story.append(Paragraph(
        "Each claim was matched with evidence by hybrid retrieval (BM25 + dense vectors) and then checked with "
        "natural language inference. Retrieval similarity only finds candidate evidence; it is never used as proof.",
        st["small"]))
    story.append(Spacer(1, 6))
    for c in claims:
        fg, bg, _label = STATUS_COLORS.get(c["status"], STATUS_COLORS[STATUS_INSUFFICIENT])
        sc = c.get("scores", {})
        head = Table([[Paragraph(f'<b>{_t(c["id"])}</b>', st["small"]), _pill(c["status"], st),
                       Paragraph(f'Confidence {c.get("confidence", 0):.0%}', st["small"])]],
                     colWidths=[16 * mm, 50 * mm, None])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        scores = Table([[Paragraph("Entailment", st["small"]), Paragraph("Contradiction", st["small"]),
                         Paragraph("Neutral", st["small"])],
                        [Paragraph(f'<b>{sc.get("entailment", 0):.1%}</b>', st["body"]),
                         Paragraph(f'<b>{sc.get("contradiction", 0):.1%}</b>', st["body"]),
                         Paragraph(f'<b>{sc.get("neutral", 0):.1%}</b>', st["body"])]],
                       colWidths=[width / 3] * 3)
        scores.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        block: list = [head, Spacer(1, 3), Paragraph(_t(c["text"]), st["claim"]), Spacer(1, 3), scores, Spacer(1, 4),
                       Paragraph(f'<b>Explanation.</b> {_t(c.get("explanation", ""))}', st["body"])]
        if c.get("needs_review"):
            reasons = " ".join(REASON_TEXT.get(r, r) for r in c.get("review_reasons", []))
            warn = Table([[Paragraph(f"<b>Human review recommended.</b> {_t(reasons)}", st["warn"])]], colWidths=[width])
            warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
                                      ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#FCD34D")),
                                      ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            block += [Spacer(1, 4), warn]
        ev = c.get("evidence", [])
        if ev:
            block.append(Spacer(1, 5))
            block.append(Paragraph("Evidence", st["h2"]))
        story.append(KeepTogether(block[:6]))
        story.extend(block[6:])
        for k, e in enumerate(ev[:5], start=1):
            n = e.get("nli", {})
            rel = {"supports": "supports", "contradicts": "contradicts"}.get(e.get("relation"), "neutral")
            story.append(KeepTogether([
                Paragraph(f'<b>[{k}] {_t(e.get("doc_name", ""))}</b>, page {e.get("page", "?")} '
                          f'<font color="#64748B">- {rel}; E {n.get("entailment", 0):.0%} / C {n.get("contradiction", 0):.0%} '
                          f'/ N {n.get("neutral", 0):.0%}; retrieval rank {e.get("rank", "?")}, '
                          f'BM25 {e.get("bm25_score") if e.get("bm25_score") is not None else "-"}, '
                          f'dense {e.get("dense_score") if e.get("dense_score") is not None else "-"}</font>', st["small"]),
                Paragraph(_t(e.get("text", "")), st["quote"]), Spacer(1, 3)]))
        story += [Spacer(1, 4), HRFlowable(width="100%", thickness=0.5, color=LINE), Spacer(1, 6)]

    # --- limitations ---------------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("4. Limitations and disclaimer", st["h1"]))
    for line in (
        "<b>Only as good as the documents.</b> A claim can only be supported or contradicted by the reference "
        "documents you supplied. 'Insufficient evidence' does not mean a claim is false; it means these documents say nothing decisive.",
        "<b>Automatic claim extraction is heuristic.</b> Compound sentences may be split imperfectly. Review the claims for important decisions.",
        "<b>NLI models make mistakes.</b> Negation, numbers, dates, long context and implicit reasoning can be misjudged. "
        "Scores are model probabilities, not guarantees.",
        "<b>Retrieval can miss evidence.</b> If the right passage is not retrieved, the claim is reported as insufficient evidence.",
        "<b>Conflicting sources are not resolved.</b> When trusted sources disagree, the claim is flagged for a human decision.",
        "<b>Not professional advice.</b> This report is a verification aid. It is not legal, medical or financial advice, and it must "
        "not be the only basis for safety-critical decisions.",
    ):
        story += [Paragraph(line, st["body"]), Spacer(1, 4)]
    story += [Spacer(1, 6), Paragraph(f"Generated by {APP_NAME} v{APP_VERSION}.", st["small"])]

    def on_page(canvas, d):
        _header_band(canvas, d)
        _footer(canvas, d, sid)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
