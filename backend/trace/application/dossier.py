"""Case dossier PDF (reportlab). Decision support only; the draft report is never submitted."""

from __future__ import annotations

import io
from typing import Any

import networkx as nx
from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from trace.domain.guardrails.policy import DOSSIER_FOOTER, DRAFT_WATERMARK

_TYPE_COLOUR = {"account": colors.HexColor("#3b82f6"), "customer": colors.HexColor("#22c55e"),
                "device": colors.HexColor("#f59e0b"), "ip": colors.HexColor("#a855f7"),
                "merchant": colors.HexColor("#ef4444")}


def _graph_drawing(case: dict[str, Any], graph: dict[str, Any], w: float = 170 * mm, h: float = 90 * mm) -> Drawing:
    d = Drawing(w, h)
    g = nx.Graph()
    for n in graph["nodes"]:
        g.add_node(n["id"], **n)
    for e in graph["edges"]:
        g.add_edge(e["source"], e["target"], suspicious=e.get("suspicious", False))
    if not g:
        d.add(String(10, h / 2, "No graph data", fontSize=9))
        return d
    pos = nx.spring_layout(g, seed=0)
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    span_x, span_y = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1

    def xy(n):
        x, y = pos[n]
        return 10 + (x - min(xs)) / span_x * (w - 20), 10 + (y - min(ys)) / span_y * (h - 20)

    for u, v, data in g.edges(data=True):
        (x1, y1), (x2, y2) = xy(u), xy(v)
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.red if data["suspicious"] else colors.lightgrey, strokeWidth=0.6))
    for n, data in g.nodes(data=True):
        x, y = xy(n)
        d.add(Circle(x, y, 3, fillColor=_TYPE_COLOUR.get(data.get("type"), colors.grey), strokeColor=None))
    return d


def _table(rows: list[list[Any]], widths=None) -> Table:
    st = getSampleStyleSheet()["BodyText"]
    st.fontSize = 7
    st.leading = 8.5
    t = Table([[Paragraph(str(c), st) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def build_dossier(case: dict[str, Any], graph: dict[str, Any], audit: list[dict[str, Any]], audit_valid: bool) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    H, P = styles["Heading2"], styles["BodyText"]

    def on_page(canvas, doc, draft=False):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(15 * mm, 10 * mm, f"{DOSSIER_FOOTER}  |  Case {case['id']}  |  page {doc.page}")
        if draft:
            canvas.setFont("Helvetica-Bold", 22)
            canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.18))
            canvas.translate(105 * mm, 150 * mm)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "DRAFT - Requires human review.")
            canvas.drawCentredString(0, -28, "Not submitted. No determination made.")
        canvas.restoreState()

    sb = case["score_breakdown"]
    els: list[Any] = [Paragraph(f"TRACE case dossier — {case['id']}", styles["Title"]),
                      Paragraph(case["guardrail_notice"], P), Spacer(1, 4 * mm),
                      Paragraph("Summary", H), Paragraph(case["summary"], P),
                      Paragraph(f"Tier <b>{case['tier']}</b> · priority score <b>{case['priority_score']:g}</b> "
                                f"(priority score, not a probability) · status {case['status']}", P),
                      Paragraph(f"Exposure on flagged transactions: {case['exposure']['total']:,.2f} "
                                f"over {case['exposure']['suspicious_txns']} transactions", P),
                      Paragraph("Network snapshot", H), _graph_drawing(case, graph),
                      Paragraph("Evidence", H),
                      _table([["ID", "Type", "Source", "Description", "Rows"]] +
                             [[e["id"], e["finding_type"], e["source"], e["description"], e["n_source_rows"]]
                              for e in case["evidence"]], [12 * mm, 30 * mm, 20 * mm, 95 * mm, 12 * mm]),
                      Paragraph("Hypotheses", H),
                      _table([["Hypothesis", "Support", "Evidence for", "Evidence against", "Not observed"]] +
                             [[h["label"], f"{h['support']:.2f}", ", ".join(h["evidence_for"]),
                               ", ".join(h["evidence_against"]) or "-", ", ".join(h["missing_signals"]) or "-"]
                              for h in case["hypotheses"]]),
                      Paragraph("Legitimate explanations considered", H),
                      _table([["Alternative", "Status", "Fit", "Reason"]] +
                             [[a["label"], a["status"], "-" if a["fit"] is None else f"{a['fit']:.2f}", a["reason"]]
                              for a in case["alternatives"]], [40 * mm, 25 * mm, 12 * mm, 92 * mm]),
                      Paragraph("Score breakdown", H),
                      _table([["Component", "Weight", "Strength", "Points"]] +
                             [[s["signal"], s["weight"], f"{s['strength']:.2f}", s["points"]] for s in sb["signals"]] +
                             [[f"{s['signal']} (model)", s["weight"], f"{s['strength']:.2f}", s["points"]] for s in sb["ml_signals"]] +
                             [["ML cap applied", "", "", f"{sb['ml_capped_total']} of {sb['ml_raw_total']}"],
                              ["Bonus (extra signal types)", "", "", sb["bonus"]]] +
                             [[f"Penalty: {p['alternative']}", p["weight"], f"fit {p['fit']:.2f}", p["points"]] for p in sb["penalties"]] +
                             [["Total", "", "", f"{sb['total']} ({sb['tier']})"]]),
                      Paragraph("Counterfactuals", H),
                      _table([["Removed", "Score", "Tier", "Lowers tier", "Still opens case"]] +
                             [[", ".join(c["removed"]), c["score"], c["tier"], c["lowers_tier"], c["still_opens_case"]]
                              for c in case["counterfactuals"]]),
                      Paragraph("Recommended next steps (for the investigator)", H),
                      _table([["Step", "Why"]] + [[s["label"], s["reason"]] for s in case["next_steps"]]),
                      Paragraph(f"Review history (audit chain {'verified' if audit_valid else 'FAILED verification'})", H),
                      _table([["#", "Time", "Reviewer", "Action", "Notes"]] +
                             [[a["seq"], a["ts"], a["actor"], a["action"], a["payload"].get("notes") or a["payload"].get("note", "")]
                              for a in audit]) if audit else Paragraph("No human review recorded yet.", P)]

    els += [NextPageTemplate("draft"), PageBreak(), Paragraph("DRAFT regulatory-style report template", styles["Title"]),
            Paragraph(DRAFT_WATERMARK, P), Spacer(1, 4 * mm),
            Paragraph("This template is pre-filled from the case for a human investigator to complete, verify and decide "
                      "upon. TRACE has no submission integration and has not submitted anything.", P),
            Paragraph("Subjects", H), Paragraph(", ".join(e["id"] for e in case["entities"] if e["role"] == "member"), P),
            Paragraph("Activity description (to be verified by the investigator)", H),
            *[Paragraph(f"[{e['id']}] {e['description']}", P) for e in case["evidence"] if e["source"] == "deterministic"],
            Paragraph("Investigator determination", H), Paragraph("[To be completed by a human investigator]", P)]
    doc = BaseDocTemplate(buf, pagesize=A4, title=f"TRACE dossier {case['id']}")
    frame = Frame(15 * mm, 18 * mm, A4[0] - 30 * mm, A4[1] - 33 * mm)
    doc.addPageTemplates([PageTemplate("main", [frame], onPage=on_page),
                          PageTemplate("draft", [frame], onPage=lambda c, d: on_page(c, d, draft=True))])
    doc.build(els)
    return buf.getvalue()
