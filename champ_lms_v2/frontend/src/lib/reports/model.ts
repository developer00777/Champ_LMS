/**
 * The analysis behind the downloadable admin report.
 *
 * Both exports — CSV and PDF — read this one model rather than the raw
 * `TestResults` payload, so a spreadsheet and the printed board can never
 * disagree about who is a Champion or which topic is the weakest.
 */
import type { CohortCoaching, TestResults, TestResultRow, TopicStat } from '$lib/api/client';

export type BandKey = 'champion' | 'on_track' | 'at_risk' | 'lagging';

export interface BandSpec {
  key: BandKey;
  label: string;
  /** Human range, e.g. "85+%" — printed in the legend and in the CSV. */
  range: string;
  min: number;
  max: number;
  color: string;
}

export interface ReportPerson {
  rank: number;
  userId: string;
  name: string;
  employeeCode: string | null;
  email: string | null;
  department: string | null;
  score: number;
  marksEarned: number;
  marksTotal: number;
  correct: number;
  questions: number;
  passed: boolean;
  band: BandSpec;
  submittedAt: string;
  riskLevel: string | null;
  riskScore: number | null;
  topics: Record<string, TopicStat>;
  /** Cached AI insight, when an admin generated one for this attempt. */
  aiFocus: string | null;
}

export interface ReportTopic {
  topic: string;
  correct: number;
  total: number;
  accuracy: number;
  /** How many people got nothing right on this topic. */
  zeroCount: number;
  /** How many got everything right. */
  perfectCount: number;
}

export interface ReportBand extends BandSpec {
  people: ReportPerson[];
  share: number;
}

export interface TestReportModel {
  title: string;
  generatedAt: Date;
  passThreshold: number;
  totalQuestions: number;
  attemptCount: number;
  averageScore: number;
  passRate: number;
  topScore: number;
  lowScore: number;
  /** Everyone tied on the highest score — the board shares the lead rather than ranking a tie. */
  leaders: ReportPerson[];
  people: ReportPerson[];
  bands: ReportBand[];
  topics: ReportTopic[];
  weakest: ReportTopic | null;
  strongest: ReportTopic | null;
  passedCount: number;
  /** At Risk + Lagging combined — the group needing intervention. */
  needsWorkCount: number;
  flaggedCount: number;
  narrative: string;
  recommendations: string[];
  /** True when the narrative and actions came from the AI coaching panel. */
  aiAssisted: boolean;
}

/**
 * Band edges are derived from the test's own pass mark rather than hardcoded,
 * so a 50%-pass test and a 90%-pass test both produce a sensible spread.
 */
export function bandSpecs(passThreshold: number): BandSpec[] {
  const pass = Math.min(95, Math.max(20, Math.round(passThreshold)));
  const champion = Math.min(96, Math.max(pass + 10, 85));
  const atRisk = Math.max(10, pass - 20);
  return [
    { key: 'champion', label: 'Champions', range: `${champion}+%`, min: champion, max: 100, color: '#0d7a4f' },
    { key: 'on_track', label: 'On Track', range: `${pass}-${champion - 1}%`, min: pass, max: champion - 1, color: '#1f6feb' },
    { key: 'at_risk', label: 'At Risk', range: `${atRisk}-${pass - 1}%`, min: atRisk, max: pass - 1, color: '#c8791a' },
    { key: 'lagging', label: 'Lagging', range: `Below ${atRisk}%`, min: 0, max: atRisk - 1, color: '#c0392b' },
  ];
}

function bandFor(score: number, specs: BandSpec[]): BandSpec {
  return specs.find((b) => score >= b.min && score <= b.max) ?? specs[specs.length - 1];
}

function displayName(a: TestResultRow): string {
  return a.full_name || a.email || 'Unknown';
}

/** Latest attempt per person: reporting a score someone already beat is misleading. */
function latestPerLearner(attempts: TestResultRow[]): TestResultRow[] {
  const latest = new Map<string, TestResultRow>();
  for (const a of attempts) {
    const held = latest.get(a.user_id);
    if (!held || new Date(a.submitted_at) > new Date(held.submitted_at)) latest.set(a.user_id, a);
  }
  return [...latest.values()];
}

export function buildTestReport(
  data: TestResults,
  coaching: CohortCoaching | null = null,
): TestReportModel {
  const specs = bandSpecs(data.pass_threshold);
  const rows = latestPerLearner(data.attempts).sort(
    (a, b) => b.score - a.score || displayName(a).localeCompare(displayName(b)),
  );

  const people: ReportPerson[] = rows.map((a, i) => ({
    rank: i + 1,
    userId: a.user_id,
    name: displayName(a),
    employeeCode: a.employee_code,
    email: a.email,
    department: a.department,
    score: a.score,
    marksEarned: a.marks_earned,
    marksTotal: a.marks_total,
    correct: a.correct_count,
    questions: a.total_questions,
    passed: a.passed,
    band: bandFor(a.score, specs),
    submittedAt: a.submitted_at,
    riskLevel: a.proctoring?.risk_level ?? null,
    riskScore: a.proctoring?.risk_score ?? null,
    topics: a.topic_stats,
    aiFocus: a.ai_analysis?.suggested_focus ?? a.ai_analysis?.summary ?? null,
  }));

  const scores = people.map((p) => p.score);
  const topScore = scores.length ? Math.max(...scores) : 0;
  const lowScore = scores.length ? Math.min(...scores) : 0;

  const topics: ReportTopic[] = Object.entries(data.cohort_topic_stats)
    .map(([topic, s]) => ({
      topic,
      correct: s.correct,
      total: s.total,
      accuracy: s.accuracy,
      zeroCount: people.filter((p) => p.topics[topic] && p.topics[topic].correct === 0).length,
      perfectCount: people.filter((p) => p.topics[topic] && p.topics[topic].accuracy === 100).length,
    }))
    .sort((a, b) => b.accuracy - a.accuracy);

  const weakest = topics.length ? topics[topics.length - 1] : null;
  const strongest = topics.length ? topics[0] : null;

  const bands: ReportBand[] = specs.map((b) => {
    const inBand = people.filter((p) => p.band.key === b.key);
    return {
      ...b,
      people: inBand,
      share: people.length ? Math.round((inBand.length / people.length) * 100) : 0,
    };
  });

  const leaders = people.filter((p) => p.score === topScore);
  const passedCount = people.filter((p) => p.passed).length;
  const needsWorkCount = bands
    .filter((b) => b.key === 'at_risk' || b.key === 'lagging')
    .reduce((n, b) => n + b.people.length, 0);

  return {
    title: data.title,
    generatedAt: new Date(),
    passThreshold: data.pass_threshold,
    totalQuestions: data.total_questions,
    attemptCount: people.length,
    averageScore: scores.length
      ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
      : 0,
    passRate: people.length ? Math.round((passedCount / people.length) * 100) : 0,
    topScore,
    lowScore,
    leaders,
    people,
    bands,
    topics,
    weakest,
    strongest,
    passedCount,
    needsWorkCount,
    flaggedCount: people.filter(
      (p) => p.riskLevel === 'suspicious' || p.riskLevel === 'high_risk',
    ).length,
    narrative: buildNarrative(people, weakest, strongest, coaching),
    recommendations: buildRecommendations(people, bands, weakest, leaders, coaching),
    aiAssisted: Boolean(coaching),
  };
}

function nameList(people: ReportPerson[], limit = 4): string {
  const names = people.slice(0, limit).map((p) => p.name);
  const rest = people.length - names.length;
  const joined =
    names.length > 1
      ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
      : (names[0] ?? '');
  return rest > 0 ? `${joined} +${rest} more` : joined;
}

function buildNarrative(
  people: ReportPerson[],
  weakest: ReportTopic | null,
  strongest: ReportTopic | null,
  coaching: CohortCoaching | null,
): string {
  if (coaching?.guidance?.cohort_summary) return coaching.guidance.cohort_summary;
  if (!weakest || !people.length) return 'Not enough graded attempts yet to read a pattern.';

  const parts = [
    `${weakest.topic} is the cohort's clearest gap — the group is averaging ${weakest.accuracy}% on it` +
      (strongest && strongest.topic !== weakest.topic
        ? `, against ${strongest.accuracy}% on ${strongest.topic}.`
        : '.'),
  ];
  if (weakest.zeroCount > 0) {
    parts.push(
      `${weakest.zeroCount} of ${people.length} scored nothing at all here` +
        (weakest.perfectCount
          ? `, while ${weakest.perfectCount} answered every question on it correctly.`
          : '.'),
    );
  }
  const belowPass = people.filter((p) => !p.passed);
  if (belowPass.length) {
    parts.push(
      `${belowPass.length} of ${people.length} finished below the pass mark (${nameList(belowPass)}).`,
    );
  }
  return parts.join(' ');
}

function buildRecommendations(
  people: ReportPerson[],
  bands: ReportBand[],
  weakest: ReportTopic | null,
  leaders: ReportPerson[],
  coaching: CohortCoaching | null,
): string[] {
  const recs: string[] = [];
  if (coaching?.guidance?.group_actions?.length) recs.push(...coaching.guidance.group_actions);

  if (weakest) {
    recs.push(
      `Prioritise coaching on ${weakest.topic} — the weakest area at ${weakest.accuracy}% ` +
        `(${weakest.correct} of ${weakest.total} answers correct across the cohort). Closing half ` +
        `that gap moves most of the On Track group into Champion range.`,
    );
    const strongOnWeak = people.filter((p) => (p.topics[weakest.topic]?.accuracy ?? 0) === 100);
    const zeroOnWeak = people.filter((p) => p.topics[weakest.topic]?.correct === 0);
    if (strongOnWeak.length && zeroOnWeak.length) {
      recs.push(
        `Pair the ${strongOnWeak.length} who scored full marks on ${weakest.topic} ` +
          `(${nameList(strongOnWeak)}) with the ${zeroOnWeak.length} who scored none ` +
          `(${nameList(zeroOnWeak)}) for shadowed practice.`,
      );
    }
  }

  const lagging = bands.find((b) => b.key === 'lagging')?.people ?? [];
  if (lagging.length) {
    recs.push(
      `Give the Lagging group (${nameList(lagging, 6)}) a written 1:1 plan — each is short on more ` +
        `than one area at once, so a single blanket fix will not close the gap.`,
    );
  }

  // Someone capable but with whole topics at zero is worth naming: that shape
  // is fixable far faster than a flat low score.
  const outlier = people.find((p) => {
    const entries = Object.values(p.topics);
    const zeros = entries.filter((t) => t.correct === 0).length;
    return !p.passed && zeros >= 2 && entries.some((t) => t.accuracy >= 80);
  });
  if (outlier) {
    const zeros = Object.entries(outlier.topics)
      .filter(([, t]) => t.correct === 0)
      .map(([t]) => t);
    recs.push(
      `${outlier.name} is a specific outlier — strong on some areas but zero on ` +
        `${zeros.join(', ')}. A targeted push on those could lift the total quickly.`,
    );
  }

  if (leaders.length) {
    recs.push(
      leaders.length > 1
        ? `Recognise the joint leads (${nameList(leaders, 5)}) publicly this cycle — the source data ties them exactly.`
        : `Recognise ${leaders[0].name} publicly this cycle for the top score of ${leaders[0].score}%.`,
    );
  }

  const flagged = people.filter((p) => p.riskLevel === 'suspicious' || p.riskLevel === 'high_risk');
  if (flagged.length) {
    recs.push(
      `Review the ${flagged.length} attempt(s) flagged by proctoring (${nameList(flagged)}) before ` +
        `these results are treated as final.`,
    );
  }
  return recs;
}

/** File-safe slug of the test title, used for both download filenames. */
export function reportSlug(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return slug || 'test-results';
}

/** Triggers a browser download for generated report content. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke on the next tick — Safari cancels the download if the URL dies first.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
