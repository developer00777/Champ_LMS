/**
 * CSV export of the results analysis.
 *
 * Written as one sectioned sheet rather than several files: an admin opening
 * this in Excel gets the headline numbers, the band roster, the topic
 * breakdown and the full per-person table in the order they'd read them,
 * with the per-topic scores as real columns so they can pivot on them.
 */
import { downloadBlob, reportSlug, type TestReportModel } from './model';

function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  // Quote anything a spreadsheet would otherwise split or mangle.
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function row(values: unknown[]): string {
  return values.map(cell).join(',');
}

const RISK_LABELS: Record<string, string> = {
  clean: 'No issues',
  minor: 'Minor flags',
  suspicious: 'Needs review',
  high_risk: 'High risk',
};

export function buildResultsCsv(m: TestReportModel): string {
  const topicNames = m.topics.map((t) => t.topic);
  const lines: string[] = [];

  lines.push(row(['Champ LMS — test results analysis']));
  lines.push(row(['Test', m.title]));
  lines.push(row(['Generated', m.generatedAt.toISOString()]));
  lines.push(row(['Pass mark', `${m.passThreshold}%`]));
  lines.push(row(['Questions', m.totalQuestions]));
  lines.push(row(['Learners scored', m.attemptCount]));
  lines.push(row(['Team average', `${m.averageScore}%`]));
  lines.push(row(['Pass rate', `${m.passRate}%`]));
  lines.push(row(['Highest score', `${m.topScore}%`]));
  lines.push(row(['Lowest score', `${m.lowScore}%`]));
  lines.push(row(['Flagged by proctoring', m.flaggedCount]));
  lines.push('');

  lines.push(row(['Band summary']));
  lines.push(row(['Band', 'Range', 'Learners', 'Share %', 'Names']));
  for (const b of m.bands) {
    lines.push(
      row([b.label, b.range, b.people.length, b.share, b.people.map((p) => p.name).join('; ')]),
    );
  }
  lines.push('');

  lines.push(row(['Topic accuracy across the cohort']));
  lines.push(row(['Topic', 'Correct', 'Answered', 'Accuracy %', 'Scored zero', 'Scored full']));
  for (const t of m.topics) {
    lines.push(row([t.topic, t.correct, t.total, t.accuracy, t.zeroCount, t.perfectCount]));
  }
  lines.push('');

  lines.push(row(['Individual results']));
  lines.push(
    row([
      'Rank',
      'Name',
      'Employee code',
      'Email',
      'Department',
      'Score %',
      'Band',
      'Result',
      'Marks earned',
      'Marks total',
      'Correct',
      'Questions',
      'Integrity',
      'Risk score',
      'Submitted',
      ...topicNames.map((t) => `${t} %`),
      'AI focus',
    ]),
  );
  for (const p of m.people) {
    lines.push(
      row([
        p.rank,
        p.name,
        p.employeeCode,
        p.email,
        p.department,
        p.score,
        p.band.label,
        p.passed ? 'Passed' : 'Failed',
        p.marksEarned,
        p.marksTotal,
        p.correct,
        p.questions,
        p.riskLevel ? (RISK_LABELS[p.riskLevel] ?? p.riskLevel) : 'Not proctored',
        p.riskScore ?? '',
        new Date(p.submittedAt).toISOString(),
        ...topicNames.map((t) => p.topics[t]?.accuracy ?? ''),
        p.aiFocus,
      ]),
    );
  }
  lines.push('');

  lines.push(row(['Analysis']));
  lines.push(row(['Summary', m.narrative]));
  m.recommendations.forEach((r, i) => lines.push(row([`Recommendation ${i + 1}`, r])));

  return lines.join('\r\n');
}

export function downloadResultsCsv(m: TestReportModel): void {
  // BOM first: without it Excel on Windows reads the em dashes and names as
  // mojibake, which is exactly where this file is opened.
  const blob = new Blob(['﻿' + buildResultsCsv(m)], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `${reportSlug(m.title)}-analysis.csv`);
}
