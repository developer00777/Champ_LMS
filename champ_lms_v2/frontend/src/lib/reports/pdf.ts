/**
 * The downloadable leadership-board PDF for a test series.
 *
 * Laid out after the "GenZ Leadership Board" deck an admin already circulates:
 * landscape A4, a top-honours cover with the ranked field, a four-tier roster
 * with band composition, and a closing page of what to do about it.
 *
 * The source deck's per-person heat-map page is deliberately NOT reproduced —
 * it is the one page that does not survive a cohort of any real size, and it
 * was excluded from this report by request.
 *
 * Real vector text, not a screenshot: it stays searchable, selectable and
 * legible when printed, and carries PDF bookmarks plus clickable page nav.
 */
import { downloadBlob, reportSlug, type ReportPerson, type TestReportModel } from './model';

// Landscape A4, in millimetres.
const W = 297;
const H = 210;
const M = 14; // page margin
const CONTENT = W - M * 2;

const INK = '#14141e';
const MUTED = '#6f6f80';
const HAIRLINE = '#d9d9e2';
const PANEL = '#f5f5f9';
const ACCENT = '#e50914';

type Doc = import('jspdf').jsPDF;

/**
 * jsPDF's built-in fonts are WinAnsi-encoded, so typographic punctuation from
 * AI-written narrative text would drop out. Fold it to ASCII equivalents.
 */
function safe(text: unknown): string {
  return String(text ?? '')
    .replace(/[—–]/g, '-')
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/…/g, '...')
    .replace(/·/g, '-');
}

function text(
  doc: Doc,
  value: unknown,
  x: number,
  y: number,
  opts: { size?: number; bold?: boolean; color?: string; align?: 'left' | 'center' | 'right'; maxWidth?: number } = {},
): void {
  doc.setFont('helvetica', opts.bold ? 'bold' : 'normal');
  doc.setFontSize(opts.size ?? 9);
  doc.setTextColor(opts.color ?? INK);
  doc.text(safe(value), x, y, { align: opts.align ?? 'left', maxWidth: opts.maxWidth });
}

/** Wrapped paragraph. Returns the y position just below the last line. */
function paragraph(
  doc: Doc,
  value: unknown,
  x: number,
  y: number,
  width: number,
  opts: { size?: number; bold?: boolean; color?: string; leading?: number } = {},
): number {
  const size = opts.size ?? 8.5;
  const leading = opts.leading ?? size * 0.46;
  doc.setFont('helvetica', opts.bold ? 'bold' : 'normal');
  doc.setFontSize(size);
  doc.setTextColor(opts.color ?? INK);
  const lines: string[] = doc.splitTextToSize(safe(value), width);
  lines.forEach((line, i) => doc.text(line, x, y + i * leading));
  return y + (lines.length - 1) * leading;
}

/** Small-caps-ish eyebrow label: letterspaced uppercase, used as section marks. */
function eyebrow(doc: Doc, value: string, x: number, y: number, color = MUTED, size = 6.6): void {
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(size);
  doc.setTextColor(color);
  doc.text(safe(value).toUpperCase(), x, y, { charSpace: 0.5 });
}

/** Single-line fit: truncates rather than wrapping, so a long name can never
 * spill into the row beneath it. */
function fit(doc: Doc, value: unknown, width: number, size: number, bold = false): string {
  doc.setFont('helvetica', bold ? 'bold' : 'normal');
  doc.setFontSize(size);
  let out = safe(value);
  if (doc.getTextWidth(out) <= width) return out;
  while (out.length > 1 && doc.getTextWidth(`${out}...`) > width) out = out.slice(0, -1);
  return `${out.trimEnd()}...`;
}

/** Largest size (down to `min`) at which the text still fits on one line. */
function fitSize(doc: Doc, value: unknown, width: number, max: number, min: number, bold = true): number {
  doc.setFont('helvetica', bold ? 'bold' : 'normal');
  let size = max;
  while (size > min) {
    doc.setFontSize(size);
    if (doc.getTextWidth(safe(value)) <= width) break;
    size -= 0.5;
  }
  return size;
}

function rule(doc: Doc, x: number, y: number, width: number, color = HAIRLINE): void {
  doc.setDrawColor(color);
  doc.setLineWidth(0.2);
  doc.line(x, y, x + width, y);
}

function box(doc: Doc, x: number, y: number, w: number, h: number, fill: string, radius = 1.6): void {
  doc.setFillColor(fill);
  doc.roundedRect(x, y, w, h, radius, radius, 'F');
}

// ---------------------------------------------------------------------------
// Page 1 — top honours, headline numbers, ranked field
// ---------------------------------------------------------------------------
function coverPage(doc: Doc, m: TestReportModel): void {
  const joint = m.leaders.length > 1;

  // Shrunk to one line instead of wrapped: everything below the title sits at a
  // fixed y, so a two-line title would land on top of the subtitle.
  const titleSize = fitSize(doc, m.title, CONTENT - 60, 21, 12);
  text(doc, fit(doc, m.title, CONTENT - 60, titleSize, true), M, 32, {
    size: titleSize,
    bold: true,
  });
  // The excluded count is printed rather than silently applied: these figures
  // will be read next to the on-screen ones, which still count every attempt.
  const excluded =
    m.excludedStaffCount > 0
      ? ` - ${m.excludedStaffCount} staff attempt${m.excludedStaffCount === 1 ? '' : 's'} excluded`
      : '';
  text(
    doc,
    `Results report - pass mark ${m.passThreshold}% - ${m.totalQuestions} questions - ` +
      `${m.attemptCount} learner${m.attemptCount === 1 ? '' : 's'} scored${excluded}`,
    M,
    39,
    { size: 8.5, color: MUTED },
  );
  rule(doc, M, 44, CONTENT);

  // --- left: top honours -------------------------------------------------
  const leftW = 178;
  eyebrow(doc, joint ? 'Top honours - joint lead' : 'Top honours', M, 53, ACCENT, 7);

  const honoursCopy = joint
    ? `${m.leaders.length} learners closed this cycle level on points, each posting the highest score of ` +
      `${m.topScore}%. Recognition is shared rather than ranked, since the source data ties them exactly.`
    : m.people.length === 1
      ? `${m.leaders[0].name} is the only graded attempt so far, at ${m.topScore}%.`
      : m.leaders.length === 1
        ? `${m.leaders[0].name} posted the highest score of the cycle at ${m.topScore}%, ` +
          `${m.topScore - (m.people[1]?.score ?? m.topScore)} points clear of the next result.`
        : 'No graded attempts yet.';
  paragraph(doc, honoursCopy, M, 60, leftW - 4, { size: 8.6, color: '#3a3a4a', leading: 4.2 });

  const shown = m.leaders.slice(0, 4);
  const cardW = shown.length ? Math.min(54, (leftW - 6 * (shown.length - 1)) / shown.length) : 0;
  shown.forEach((p, i) => {
    const x = M + i * (cardW + 6);
    box(doc, x, 74, cardW, 26, PANEL, 2);
    doc.setFillColor(p.band.color);
    doc.rect(x, 74, 1.6, 26, 'F');
    text(doc, fit(doc, p.name, cardW - 9, 9.6, true), x + 5, 82, { size: 9.6, bold: true });
    text(doc, `${p.score}%`, x + 5, 92, { size: 15, bold: true, color: p.band.color });
    text(doc, `${p.marksEarned}/${p.marksTotal} marks`, x + 5, 97, { size: 6.8, color: MUTED });
  });
  if (m.leaders.length > shown.length) {
    text(doc, `+${m.leaders.length - shown.length} more tied`, M, 105, { size: 7, color: MUTED });
  }

  // --- right: headline numbers -------------------------------------------
  const rx = M + leftW + 8;
  const rw = CONTENT - leftW - 8;
  box(doc, rx, 49, rw, 51, PANEL, 2);
  eyebrow(doc, 'Team average', rx + 6, 57);
  text(doc, `${m.averageScore}%`, rx + rw - 6, 62, { size: 20, bold: true, align: 'right' });

  const stats: [string, string][] = [
    ['Highest to lowest', `${m.topScore} - ${m.lowScore}`],
    ['Passed the mark', `${m.passedCount} of ${m.attemptCount}`],
    ['At Risk + Lagging', `${m.needsWorkCount}`],
  ];
  stats.forEach(([label, value], i) => {
    const y = 74 + i * 9;
    text(doc, label, rx + 6, y, { size: 7.6, color: MUTED });
    text(doc, value, rx + rw - 6, y, { size: 9.4, bold: true, align: 'right' });
    if (i < stats.length - 1) rule(doc, rx + 6, y + 3, rw - 12, '#e6e6ee');
  });

  // --- scoring bands (clickable: jumps to the roster page) ----------------
  eyebrow(doc, 'How the board is scored', M, 112);
  const named = m.topics.slice(0, 4).map((t) => t.topic);
  const extra = m.topics.length - named.length;
  const topicLine = m.topics.length
    ? `Score out of 100 - ${named.join(' - ')}${extra > 0 ? ` +${extra} more` : ''}`
    : 'Score out of 100 - no topics tagged';
  text(doc, fit(doc, topicLine, CONTENT - 62, 7), M + CONTENT, 112, {
    size: 7,
    color: MUTED,
    align: 'right',
  });
  const chipW = (CONTENT - 6 * 3) / 4;
  m.bands.forEach((b, i) => {
    const x = M + i * (chipW + 6);
    box(doc, x, 116, chipW, 11, PANEL, 1.6);
    doc.setFillColor(b.color);
    doc.rect(x, 116, 1.6, 11, 'F');
    text(doc, b.label, x + 5, 121.5, { size: 8.4, bold: true, color: b.color });
    text(doc, b.range, x + chipW - 5, 121.5, { size: 7.6, color: MUTED, align: 'right' });
    text(doc, `${b.people.length} learner${b.people.length === 1 ? '' : 's'}`, x + 5, 125.6, {
      size: 6.6,
      color: MUTED,
    });
    doc.link(x, 116, chipW, 11, { pageNumber: 2 });
  });

  // --- ranked field ------------------------------------------------------
  eyebrow(doc, 'Full field, ranked by score', M, 138);
  text(doc, `All ${m.attemptCount} learners, latest attempt`, M + CONTENT, 138, {
    size: 7,
    color: MUTED,
    align: 'right',
  });
  rankedBars(doc, m.people, 143, 187);
}

/**
 * The ranked column chart. Bars are coloured by band so the tiers read at a
 * glance. Past roughly twenty learners a horizontal name no longer fits its
 * slot, so the labels turn on their side rather than wrapping into each other.
 */
function rankedBars(doc: Doc, people: ReportPerson[], top: number, bottomLimit: number): void {
  if (!people.length) return;
  const slot = CONTENT / people.length;
  const dense = slot < 13;
  // Value labels stop being readable long before the bars do.
  const showValues = slot >= 6;

  const labelSpace = dense ? 20 : 9;
  const baseline = bottomLimit - labelSpace;
  const maxH = baseline - top - (showValues ? 6 : 2);
  const barW = Math.min(15, slot * 0.62);

  rule(doc, M, baseline, CONTENT, '#c9c9d4');
  people.forEach((p, i) => {
    const cx = M + slot * i + slot / 2;
    const h = Math.max(1.2, (p.score / 100) * maxH);
    doc.setFillColor(p.band.color);
    doc.roundedRect(cx - barW / 2, baseline - h, barW, h, 0.8, 0.8, 'F');
    if (showValues) {
      text(doc, `${p.score}`, cx, baseline - h - 2, {
        size: dense ? 5.6 : 7,
        bold: true,
        align: 'center',
      });
    }

    if (dense) {
      // Rotated, reading bottom-to-top, truncated to the space available.
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(5.2);
      doc.setTextColor(MUTED);
      doc.text(fit(doc, p.name, labelSpace - 2, 5.2), cx + 1.4, baseline + labelSpace - 1, {
        angle: 90,
      });
      return;
    }

    // Two lines, each truncated rather than wrapped, so a long surname cannot
    // push a third line into the footer.
    const parts = safe(p.name).split(' ');
    const first = parts[0] ?? '';
    const rest = parts.slice(1).join(' ');
    text(doc, fit(doc, first, slot, 6), cx, baseline + 4, { size: 6, align: 'center' });
    if (rest) {
      text(doc, fit(doc, rest, slot, 6), cx, baseline + 7.4, {
        size: 6,
        color: MUTED,
        align: 'center',
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Page 2 - four-tier roster, band composition, score distribution
// (the source deck's page 2 heat map is intentionally omitted)
// ---------------------------------------------------------------------------
function rosterPage(doc: Doc, m: TestReportModel): void {
  text(doc, 'Leadership board - four-tier roster', M, 32, { size: 15, bold: true });
  text(doc, 'Every learner placed by their latest score', M + CONTENT, 32, {
    size: 8,
    color: MUTED,
    align: 'right',
  });
  rule(doc, M, 37, CONTENT);

  // The page is budgeted top-down so a deep band can never run into the blocks
  // beneath it: rows get whatever height is left after the composition bar,
  // and the distribution plot is only drawn when it still fits after that.
  const ROW = 7;
  const rosterTop = 56;
  const bottomLimit = H - 16;
  const gap = 12;
  const compBlock = 26;
  const distBlock = 36;

  const roomFor = (reserved: number) =>
    Math.max(1, Math.floor((bottomLimit - reserved - gap - rosterTop) / ROW));
  const tallest = Math.max(1, ...m.bands.map((b) => b.people.length));
  const withDistribution = tallest <= roomFor(compBlock + distBlock);
  const maxRows = Math.min(tallest, roomFor(compBlock + (withDistribution ? distBlock : 0)));
  // When a band is cut short, the last slot carries the "+N more" line instead
  // of a name, so the count is never silently wrong.
  const truncated = tallest > maxRows;
  const shownRows = truncated ? maxRows - 1 : maxRows;

  const colW = (CONTENT - 6 * 3) / 4;
  m.bands.forEach((b, i) => {
    const x = M + i * (colW + 6);
    doc.setFillColor(b.color);
    doc.roundedRect(x, 44, colW, 10, 1.6, 1.6, 'F');
    text(doc, b.label, x + 4, 50.4, { size: 9, bold: true, color: '#ffffff' });
    text(doc, b.range, x + colW - 4, 50.4, { size: 7.4, color: '#ffffff', align: 'right' });

    if (!b.people.length) {
      text(doc, 'Nobody in this band', x + 4, rosterTop + 5, { size: 7.6, color: MUTED });
      return;
    }
    b.people.slice(0, shownRows).forEach((p, r) => {
      const y = rosterTop + r * ROW;
      if (r % 2 === 0) box(doc, x, y, colW, ROW, PANEL, 0.8);
      text(doc, fit(doc, p.name, colW - 22, 7.8), x + 4, y + 4.8, { size: 7.8 });
      text(doc, `${p.score}%`, x + colW - 4, y + 4.8, { size: 7.8, bold: true, align: 'right' });
    });
    if (b.people.length > shownRows) {
      text(doc, `+${b.people.length - shownRows} more`, x + 4, rosterTop + shownRows * ROW + 4.8, {
        size: 7,
        color: MUTED,
      });
    }
  });

  const rosterBottom = rosterTop + Math.min(tallest, maxRows) * ROW;
  const naturalTop = Math.max(rosterBottom + gap, 112);
  const drawDistribution =
    withDistribution && naturalTop + compBlock + 4 + distBlock <= bottomLimit + 6;
  // A short roster would otherwise leave every block bunched at the top with a
  // band of white beneath; hand back half the slack so the page sits balanced.
  const used = naturalTop + compBlock + (drawDistribution ? 4 + distBlock : 0);
  const compY = naturalTop + Math.max(0, bottomLimit - used) * 0.5;

  composition(doc, m, compY);
  if (drawDistribution) scoreDistribution(doc, m, compY + compBlock + 4);
}

/** The stacked share bar: how much of the cohort sits in each tier. */
function composition(doc: Doc, m: TestReportModel, y: number): void {
  eyebrow(doc, 'Band composition', M, y - 8);
  text(doc, `Share of the ${m.attemptCount}-learner cohort in each tier`, M + CONTENT, y - 8, {
    size: 7,
    color: MUTED,
    align: 'right',
  });

  let x = M;
  m.bands.forEach((b) => {
    if (!b.people.length) return;
    const w = (b.people.length / Math.max(1, m.attemptCount)) * CONTENT;
    doc.setFillColor(b.color);
    doc.rect(x, y, w, 13, 'F');
    if (w > 14) {
      text(doc, `${b.people.length}`, x + w / 2, y + 8.6, {
        size: 11,
        bold: true,
        color: '#ffffff',
        align: 'center',
      });
    }
    x += w;
  });

  let lx = M;
  m.bands.forEach((b) => {
    if (!b.people.length) return;
    const w = (b.people.length / Math.max(1, m.attemptCount)) * CONTENT;
    doc.setFillColor(b.color);
    doc.circle(lx + 1.6, y + 18.4, 1.4, 'F');
    text(doc, `${b.label} ${b.people.length} - ${b.share}%`, lx + 4.6, y + 19.4, {
      size: 7.4,
      color: '#3a3a4a',
      maxWidth: Math.max(w, 40),
    });
    lx += w;
  });
}

/** Mixes a hex colour towards white — band tints for the distribution track. */
function tint(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  const r = mix((n >> 16) & 255);
  const g = mix((n >> 8) & 255);
  const b = mix(n & 255);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/**
 * A dot plot of every score on a 0-100 axis, banded behind and marked with the
 * pass line. The ranked bars on page 1 say who is ahead; this says how tightly
 * the cohort is bunched, which is what decides whether one fix moves the group.
 */
function scoreDistribution(doc: Doc, m: TestReportModel, y: number): void {
  eyebrow(doc, 'Score distribution', M, y);
  text(doc, 'One dot per learner, stacked where scores tie', M + CONTENT, y, {
    size: 7,
    color: MUTED,
    align: 'right',
  });

  const baseline = y + 22;
  const at = (score: number) => M + (Math.max(0, Math.min(100, score)) / 100) * CONTENT;

  // Banded track behind the dots.
  m.bands.forEach((b) => {
    const x0 = at(b.min);
    const x1 = at(Math.min(100, b.max + 1));
    doc.setFillColor(tint(b.color, 0.86));
    doc.rect(x0, baseline - 4, Math.max(0, x1 - x0), 6, 'F');
  });
  rule(doc, M, baseline + 2, CONTENT, '#c9c9d4');

  [0, 25, 50, 75, 100].forEach((tickValue) => {
    text(doc, `${tickValue}`, at(tickValue), baseline + 6.4, { size: 6.2, color: MUTED, align: 'center' });
  });

  // Pass mark.
  doc.setDrawColor(INK);
  doc.setLineWidth(0.4);
  doc.line(at(m.passThreshold), baseline - 6, at(m.passThreshold), baseline + 2);
  text(doc, `pass ${m.passThreshold}%`, at(m.passThreshold), baseline - 8, {
    size: 6.4,
    bold: true,
    align: 'center',
  });

  // Dots, stacked upward where several people share a score.
  const stacks = new Map<number, number>();
  for (const p of m.people) {
    const height = stacks.get(p.score) ?? 0;
    if (height >= 9) continue;
    stacks.set(p.score, height + 1);
    doc.setFillColor(p.band.color);
    doc.circle(at(p.score), baseline - 1 - height * 3.2, 1.35, 'F');
  }
  for (const [score, height] of stacks) {
    const extra = m.people.filter((p) => p.score === score).length - height;
    if (extra > 0) {
      text(doc, `+${extra}`, at(score), baseline - 3 - height * 3.2, {
        size: 5.6,
        color: MUTED,
        align: 'center',
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Page 3 — what to do about it
// ---------------------------------------------------------------------------
function insightsPage(doc: Doc, m: TestReportModel): number {
  text(doc, 'Key points for improvisation', M, 32, { size: 15, bold: true });
  text(doc, m.aiAssisted ? 'Includes AI coaching guidance' : 'Patterns behind this cycle', M + CONTENT, 32, {
    size: 8,
    color: MUTED,
    align: 'right',
  });
  rule(doc, M, 37, CONTENT);

  // --- left: accuracy per topic -----------------------------------------
  const leftW = 150;
  eyebrow(doc, 'Cohort accuracy by topic', M, 46);
  const trackX = M + 58;
  const trackW = 58;
  m.topics.forEach((t, i) => {
    const y = 54 + i * 9;
    text(doc, fit(doc, t.topic, 55, 7.8), M, y, { size: 7.8 });
    doc.setFillColor('#e8e8ef');
    doc.roundedRect(trackX, y - 3, trackW, 4, 1, 1, 'F');
    const color = t.accuracy >= 80 ? '#0d7a4f' : t.accuracy >= 50 ? '#c8791a' : '#c0392b';
    doc.setFillColor(color);
    doc.roundedRect(trackX, y - 3, Math.max(0.8, (t.accuracy / 100) * trackW), 4, 1, 1, 'F');
    text(doc, `${t.correct}/${t.total} - ${t.accuracy}%`, trackX + trackW + 4, y, {
      size: 7.4,
      bold: true,
    });
  });

  // --- right: the weakest topic, called out -------------------------------
  const rx = M + leftW + 8;
  const rw = CONTENT - leftW - 8;
  const panelH = 62;
  box(doc, rx, 42, rw, panelH, PANEL, 2);
  doc.setFillColor(ACCENT);
  doc.rect(rx, 42, 1.8, panelH, 'F');
  eyebrow(doc, m.weakest ? 'Weakest topic' : 'Summary', rx + 6, 51, ACCENT, 7);
  if (m.weakest) {
    text(doc, fit(doc, m.weakest.topic, rw - 12, 12.5, true), rx + 6, 60, { size: 12.5, bold: true });
    text(doc, `${m.weakest.accuracy}% correct across the cohort`, rx + 6, 66, {
      size: 8,
      color: MUTED,
    });
  }
  paragraph(doc, m.narrative, rx + 6, 75, rw - 12, { size: 8.2, color: '#3a3a4a', leading: 4.1 });

  // --- recommended focus --------------------------------------------------
  let y = Math.max(54 + m.topics.length * 9, 42 + panelH) + 12;
  eyebrow(doc, 'Recommended focus for the next cycle', M, y);
  y += 8;

  m.recommendations.forEach((rec, i) => {
    if (y > H - 26) {
      doc.addPage();
      y = 32;
      eyebrow(doc, 'Recommended focus (continued)', M, y);
      y += 8;
    }
    doc.setFillColor(INK);
    doc.circle(M + 2.2, y - 1.4, 2.2, 'F');
    text(doc, `${i + 1}`, M + 2.2, y - 0.2, { size: 6.4, bold: true, color: '#ffffff', align: 'center' });
    const end = paragraph(doc, rec, M + 8, y, CONTENT - 8, { size: 8.4, color: '#25252f', leading: 4.2 });
    y = end + 6.4;
  });

  // Close on the shortlist, when the page still has room for it.
  if (y + 31 <= H - 16) oneToOnes(doc, m, y + 2);
  return y;
}

/** The people to book first, with the two topics to open the conversation on. */
function oneToOnes(doc: Doc, m: TestReportModel, y: number): void {
  const focus = m.people.filter((p) => !p.passed).sort((a, b) => a.score - b.score).slice(0, 5);
  if (!focus.length) return;

  eyebrow(doc, 'Who to book first', M, y);
  text(doc, 'Lowest scores, with the two topics to open on', M + CONTENT, y, {
    size: 7,
    color: MUTED,
    align: 'right',
  });

  const cardW = (CONTENT - 6 * (focus.length - 1)) / focus.length;
  focus.forEach((p, i) => {
    const x = M + i * (cardW + 6);
    box(doc, x, y + 4, cardW, 26, PANEL, 1.6);
    doc.setFillColor(p.band.color);
    doc.rect(x, y + 4, 1.6, 26, 'F');
    text(doc, fit(doc, p.name, cardW - 24, 8.6, true), x + 5, y + 11.5, { size: 8.6, bold: true });
    text(doc, `${p.score}%`, x + cardW - 5, y + 11.5, {
      size: 9.4,
      bold: true,
      color: p.band.color,
      align: 'right',
    });
    text(doc, p.band.label, x + 5, y + 16, { size: 6.4, bold: true, color: p.band.color });
    Object.entries(p.topics)
      .sort((a, b) => a[1].accuracy - b[1].accuracy)
      .slice(0, 2)
      .forEach(([topic, st], r) => {
        text(doc, fit(doc, `${topic} - ${st.accuracy}%`, cardW - 10, 6.8), x + 5, y + 22 + r * 4.4, {
          size: 6.8,
          color: MUTED,
        });
      });
  });
}

// ---------------------------------------------------------------------------
// Chrome: running header, footer, and the clickable page nav on every page
// ---------------------------------------------------------------------------
function drawChrome(doc: Doc, m: TestReportModel, titles: string[]): void {
  const total = doc.getNumberOfPages();
  const stamp = m.generatedAt.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  for (let i = 1; i <= total; i++) {
    doc.setPage(i);
    text(doc, 'Champions Group - Champ LMS', M, 14, { size: 7.4, bold: true, color: MUTED });
    text(doc, titles[i - 1] ?? 'Report', M + CONTENT, 14, { size: 7.4, color: MUTED, align: 'right' });
    rule(doc, M, 17, CONTENT);

    rule(doc, M, H - 14, CONTENT);
    text(doc, `${m.title} - generated ${stamp}`, M, H - 9, { size: 6.8, color: MUTED });

    // Clickable page nav, so the PDF reads like the interactive board it came
    // from rather than a flat printout.
    let nx = M + CONTENT - 6 * total;
    for (let p = 1; p <= total; p++) {
      const current = p === i;
      text(doc, `${p}`, nx, H - 9, { size: 6.8, bold: current, color: current ? INK : MUTED });
      doc.link(nx - 1.5, H - 12.5, 5, 5, { pageNumber: p });
      nx += 6;
    }
  }
}

/** Builds the document. Separated from the download so it can be rendered and checked headlessly. */
export async function renderReportPdf(m: TestReportModel): Promise<Doc> {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  doc.setProperties({
    title: `${m.title} - leadership board`,
    subject: 'Test results analysis',
    creator: 'Champ LMS',
  });

  const titles: string[] = [];

  coverPage(doc, m);
  titles.push('Leadership board');

  doc.addPage();
  rosterPage(doc, m);
  titles.push('Four-tier roster');

  doc.addPage();
  insightsPage(doc, m);
  titles.push('Key points for improvisation');
  // insightsPage may have spilled onto a continuation page.
  while (titles.length < doc.getNumberOfPages()) titles.push('Key points (continued)');

  drawChrome(doc, m, titles);

  // Bookmarks. Guarded: a missing outline API must not cost the admin their
  // download, since the pages themselves are already complete.
  try {
    const outline = (doc as unknown as { outline?: { add: (p: null, t: string, o: object) => void } }).outline;
    titles.forEach((t, i) => outline?.add(null, safe(t), { pageNumber: i + 1 }));
  } catch {
    /* bookmarks are a nicety, not the deliverable */
  }

  return doc;
}

export async function downloadResultsPdf(m: TestReportModel): Promise<void> {
  const doc = await renderReportPdf(m);
  downloadBlob(doc.output('blob'), `${reportSlug(m.title)}-leadership-board.pdf`);
}

export { safe as pdfSafeText };
