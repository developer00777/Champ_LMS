"""
Integrity scoring for proctored test attempts.

Two layers, deliberately in this order:

  1. A deterministic scorer over the event timeline. It is the source of truth
     for "what happened" — counts, time away, paste sizes. It always runs, costs
     nothing, and cannot be talked out of a finding.
  2. The AI proctor, which reads that timeline plus the answer-timing profile and
     judges *intent* — the thing rules are bad at. It can raise or lower the risk
     level and must justify it in findings an admin will read.

The AI is advisory. If the model is unavailable the deterministic verdict stands
and `verdict_by` says "rules", so nobody mistakes a fallback for a judgement.
Nothing here ever fails a submit: an exception means no verdict, not a lost exam.
"""
from app.models.test_series import (
    PROCTOR_EVENT_KINDS,
    ProctorEvent,
    ProctorReport,
    TestQuestion,
)
from app.services.ai_service import ai_service

# Cap on stored events per attempt. A 60-question exam legitimately produces a
# few dozen; tens of thousands means either a broken client loop or someone
# trying to bury a real signal in noise. We keep the first N — the ones nearest
# the start are the most diagnostic — and record that truncation happened.
MAX_EVENTS = 400

# Detail strings are client-supplied and end up on an admin's screen.
MAX_DETAIL_CHARS = 200

# Weights for the deterministic risk score, out of 100. Tuned so that a single
# brief alt-tab reads as "minor" rather than branding someone a cheat, while
# leaving-the-exam-repeatedly or pasting an answer lands in "suspicious"+.
WEIGHTS = {
    "tab_hidden": 8,
    "window_blur": 4,
    "copy_attempt": 6,
    "paste_attempt": 18,
    "context_menu": 2,
    "devtools_open": 25,
    "shortcut_blocked": 5,
    "fullscreen_exit": 6,
    "answer_burst": 22,
    "multi_session": 30,
}

# Extra weight for sustained absence: a 4-minute disappearance is a different
# event from four 1-second ones even though the counts look similar.
AWAY_SECONDS_FOR_FULL_PENALTY = 180
AWAY_PENALTY_MAX = 25

RISK_BANDS = (
    (0, "clean"),
    (15, "minor"),
    (40, "suspicious"),
    (70, "high_risk"),
)


def _band(score: int) -> str:
    """Map a 0-100 risk score onto a label, highest band that the score clears."""
    label = "clean"
    for floor, name in RISK_BANDS:
        if score >= floor:
            label = name
    return label


def sanitize_events(raw: list[dict] | None) -> tuple[list[ProctorEvent], bool]:
    """
    Turn client-reported events into trusted ProctorEvents.

    Returns (events, truncated). Unknown kinds are dropped rather than stored:
    the whitelist is what keeps a tampered client from inventing categories the
    scorer and the admin UI don't understand. Bad rows are skipped individually,
    so one malformed event never costs us the rest of the timeline.
    """
    if not raw:
        return [], False

    truncated = len(raw) > MAX_EVENTS
    events: list[ProctorEvent] = []

    for row in raw[:MAX_EVENTS]:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip()
        if kind not in PROCTOR_EVENT_KINDS:
            continue

        def _int(key: str) -> int | None:
            try:
                val = row.get(key)
                if val is None:
                    return None
                # Negative offsets/durations mean a fiddled clock, not a
                # negative amount of time. Clamp instead of trusting.
                return max(0, int(float(val)))
            except (TypeError, ValueError):
                return None

        detail = row.get("detail")
        detail = str(detail)[:MAX_DETAIL_CHARS] if detail else None
        qid = row.get("question_id")

        events.append(ProctorEvent(
            kind=kind,
            at_seconds=_int("at_seconds") or 0,
            duration_seconds=_int("duration_seconds"),
            question_id=str(qid)[:64] if qid else None,
            detail=detail,
        ))

    events.sort(key=lambda e: e.at_seconds)
    return events, truncated


def score_events(events: list[ProctorEvent]) -> dict:
    """
    The deterministic pass: tally the timeline and derive a rules-only risk score.

    Returns the numbers the report needs plus the plain-language findings behind
    them, so an admin can see *why* a score is what it is even when the AI never
    ran.
    """
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind] = counts.get(e.kind, 0) + 1

    away_events = [
        e for e in events
        if e.kind in ("tab_hidden", "window_blur") and e.duration_seconds
    ]
    away_seconds = sum(e.duration_seconds or 0 for e in away_events)
    longest_away = max((e.duration_seconds or 0 for e in away_events), default=0)

    score = 0.0
    findings: list[str] = []

    for kind, weight in WEIGHTS.items():
        n = counts.get(kind, 0)
        if not n:
            continue
        # Diminishing returns: the second alt-tab is evidence, the ninth adds
        # little. Full weight for the first, a third of it for each repeat.
        score += weight + weight * 0.34 * (n - 1)

    if away_seconds:
        score += min(
            AWAY_PENALTY_MAX,
            AWAY_PENALTY_MAX * away_seconds / AWAY_SECONDS_FOR_FULL_PENALTY,
        )

    # Findings, worst-first, phrased as observations rather than accusations.
    if counts.get("multi_session"):
        findings.append(
            f"Exam was open in more than one tab or window "
            f"({counts['multi_session']}×)."
        )
    if counts.get("devtools_open"):
        findings.append(
            f"Developer tools appeared to open {counts['devtools_open']}× during "
            "the attempt."
        )
    if counts.get("answer_burst"):
        findings.append(
            f"{counts['answer_burst']} written answer(s) appeared far faster than "
            "they could be typed, which is what pasting looks like."
        )
    if counts.get("paste_attempt"):
        findings.append(f"{counts['paste_attempt']} paste attempt(s) into an answer.")
    if counts.get("copy_attempt"):
        findings.append(
            f"{counts['copy_attempt']} attempt(s) to copy question or answer text."
        )
    if counts.get("tab_hidden"):
        findings.append(
            f"Left the exam tab {counts['tab_hidden']}× "
            f"(total {away_seconds}s away, longest {longest_away}s)."
        )
    elif counts.get("window_blur"):
        findings.append(
            f"Window lost focus {counts['window_blur']}× "
            f"(total {away_seconds}s)."
        )
    if counts.get("fullscreen_exit"):
        findings.append(f"Exited exam fullscreen {counts['fullscreen_exit']}×.")
    if counts.get("shortcut_blocked"):
        findings.append(
            f"{counts['shortcut_blocked']} blocked keyboard shortcut(s) "
            "(print, save, select-all or view-source)."
        )

    risk_score = int(round(min(100.0, score)))
    return {
        "counts": counts,
        "away_seconds": away_seconds,
        "longest_away_seconds": longest_away,
        "risk_score": risk_score,
        "risk_level": _band(risk_score),
        "findings": findings,
    }


def _timeline_for_ai(events: list[ProctorEvent], limit: int = 60) -> str:
    """A compact, readable timeline. Long attempts are trimmed at both ends."""
    if len(events) > limit:
        half = limit // 2
        shown = events[:half] + events[-half:]
        gap_note = f"\n... {len(events) - limit} further events omitted ...\n"
    else:
        shown, gap_note = events, ""

    lines = []
    for i, e in enumerate(shown):
        if gap_note and i == limit // 2:
            lines.append(gap_note.strip())
        mins, secs = divmod(e.at_seconds, 60)
        bits = [f"[{mins:02d}:{secs:02d}] {e.kind}"]
        if e.duration_seconds:
            bits.append(f"for {e.duration_seconds}s")
        if e.detail:
            bits.append(f"({e.detail})")
        lines.append(" ".join(bits))
    return "\n".join(lines) or "No events recorded."


def _answer_profile(
    questions: list[TestQuestion],
    text_answers: dict[str, str],
    events: list[ProctorEvent],
) -> str:
    """
    Describe the written answers in terms the model can reason about: how long
    each is, and whether a burst event landed on that question. Length against a
    dwell time is the strongest paste signal we have without keystroke capture.
    """
    burst_qids = {e.question_id for e in events if e.kind == "answer_burst"}
    rows = []
    for q in questions:
        if not q.is_written:
            continue
        typed = (text_answers.get(q.id) or "").strip()
        if not typed:
            rows.append(f"- \"{q.question[:70]}\": left blank")
            continue
        words = len(typed.split())
        flag = " — flagged as an instant burst" if q.id in burst_qids else ""
        rows.append(f"- \"{q.question[:70]}\": {words} words{flag}")
    return "\n".join(rows) or "No written questions on this test."


async def build_report(
    raw_events: list[dict] | None,
    questions: list[TestQuestion],
    text_answers: dict[str, str],
    elapsed_seconds: int | None,
    client_reported: bool,
) -> ProctorReport:
    """
    Build the finished ProctorReport for an attempt.

    `client_reported` distinguishes "the client sent an empty event list because
    nothing happened" from "no telemetry arrived at all" — the second is itself a
    signal, since it means scripts were blocked or the submit endpoint was called
    directly.
    """
    events, truncated = sanitize_events(raw_events)
    stats = score_events(events)

    report = ProctorReport(
        events=events,
        counts=stats["counts"],
        away_seconds=stats["away_seconds"],
        longest_away_seconds=stats["longest_away_seconds"],
        telemetry_missing=not client_reported,
        risk_score=stats["risk_score"],
        risk_level=stats["risk_level"],
        findings=list(stats["findings"]),
        verdict_by="rules",
    )

    if truncated:
        report.findings.append(
            f"More than {MAX_EVENTS} integrity events were reported; only the "
            "first ones were kept."
        )
    if report.telemetry_missing:
        # Can't prove misconduct, but an unmonitored submission must not be
        # presented as a clean one.
        report.findings.append(
            "No integrity telemetry was received for this attempt — the exam "
            "monitor did not run, or the submission did not come from it."
        )
        report.risk_score = max(report.risk_score, 45)
        report.risk_level = _band(report.risk_score)

    if not ai_service.enabled:
        report.summary = _rules_summary(report)
        return report

    try:
        verdict = await ai_service.review_proctoring(
            timeline=_timeline_for_ai(events),
            counts=stats["counts"],
            away_seconds=stats["away_seconds"],
            longest_away_seconds=stats["longest_away_seconds"],
            elapsed_seconds=elapsed_seconds,
            rules_risk_score=stats["risk_score"],
            rules_findings=stats["findings"],
            answer_profile=_answer_profile(questions, text_answers, events),
            telemetry_missing=report.telemetry_missing,
        )
    except Exception:  # noqa: BLE001 — a model outage must not fail the submit
        report.summary = _rules_summary(report)
        return report

    return _apply_ai_verdict(report, verdict, rules_score=stats["risk_score"])


def _apply_ai_verdict(
    report: ProctorReport, verdict: dict, rules_score: int
) -> ProctorReport:
    """
    Fold the model's judgement into the report, clamped.

    The AI may move the score, but not below what the hard evidence supports:
    a paste that happened, happened. We let it de-escalate only a limited way
    (it can reasonably read three alt-tabs as a notification storm) and cap how
    far it can escalate on its own so a hallucinated narrative can't brand
    someone high-risk on its own authority.
    """
    try:
        ai_score = int(round(float(verdict.get("risk_score"))))
    except (TypeError, ValueError):
        ai_score = rules_score

    floor = int(rules_score * 0.6)
    ceiling = min(100, max(rules_score + 25, 25))
    final = max(floor, min(ceiling, max(0, ai_score)))

    report.risk_score = final
    # The label must match the score the clamp actually produced. The model's
    # own label is ignored when the two disagree — a verdict reading "clean" next
    # to 24/100, or "high_risk" next to 30, is what makes an admin stop trusting
    # the whole panel.
    report.risk_level = _band(final)

    summary = str(verdict.get("summary") or "").strip()
    report.summary = summary[:600] or _rules_summary(report)

    ai_findings = verdict.get("findings")
    if isinstance(ai_findings, list):
        # AI findings are additive: they explain, they don't erase the
        # deterministic record of what the client reported.
        extra = [
            str(f).strip()[:300] for f in ai_findings
            if str(f).strip() and str(f).strip() not in report.findings
        ]
        report.findings.extend(extra[:6])

    report.verdict_by = "ai"
    return report


def _rules_summary(report: ProctorReport) -> str:
    """Plain summary for when the AI never ran, so the field is never empty."""
    if report.telemetry_missing:
        return (
            "This attempt arrived without integrity telemetry, so it could not "
            "be monitored. Review it manually."
        )
    if not report.findings:
        return "No integrity issues were detected during this attempt."
    return (
        f"{len(report.findings)} integrity signal(s) recorded; risk scored "
        f"{report.risk_score}/100 by rules only (AI review unavailable)."
    )
