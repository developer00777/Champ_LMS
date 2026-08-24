/**
 * Exam lockdown + integrity telemetry for proctored test attempts.
 *
 * Two jobs, deliberately separate:
 *
 *   1. Prevention — make the obvious routes to cheating not work: selecting and
 *      copying question or answer text, right-click, paste into a written
 *      answer, print/save/view-source shortcuts.
 *   2. Observation — record what still happened (tab switches, focus loss,
 *      blocked attempts, answers that appear too fast to have been typed) so the
 *      server-side AI proctor can judge the attempt.
 *
 * None of this is security. A determined person with devtools can defeat every
 * line of it, which is exactly why the observation half exists and why the
 * verdict is formed on the server: the client's job is to raise the cost of
 * casual cheating and to report honestly, not to be unbeatable.
 *
 * Everything is scoped to the exam: `attach` returns a `detach` that puts the
 * page back as it was, so leaving the test restores normal copy/paste.
 */

export type ProctorEventKind =
  | 'tab_hidden'
  | 'tab_visible'
  | 'window_blur'
  | 'window_focus'
  | 'copy_attempt'
  | 'paste_attempt'
  | 'context_menu'
  | 'devtools_open'
  | 'shortcut_blocked'
  | 'fullscreen_exit'
  | 'answer_burst'
  | 'multi_session';

export interface ProctorEvent {
  kind: ProctorEventKind;
  at_seconds: number;
  duration_seconds?: number;
  question_id?: string;
  detail?: string;
}

export interface LockdownOptions {
  /** Called when a blocked action or excursion happens, so the UI can warn. */
  onWarn: (message: string, event: ProctorEvent) => void;
  /** The question on screen right now, for attributing events. */
  currentQuestionId: () => string | undefined;
}

/** Below this, a "paste-sized" text jump is just fast typing or autocomplete. */
const BURST_MIN_CHARS = 120;
/** Chars/second no human sustains over a burst — above it, it was pasted. */
const BURST_CHARS_PER_SECOND = 25;
/** Client-side cap, well under the server's, so the payload can't grow unbounded. */
const MAX_EVENTS = 300;

/**
 * A lockdown session. Owns its listeners and its event log for one attempt.
 */
export class ExamLockdown {
  private readonly startedAt = Date.now();
  private readonly events: ProctorEvent[] = [];
  private readonly cleanups: Array<() => void> = [];
  private readonly opts: LockdownOptions;

  /** When the page went hidden/blurred, so the return can measure the gap. */
  private awaySince: number | null = null;
  /** Last measured length per written answer, for burst detection. */
  private readonly lastLength = new Map<string, { chars: number; at: number }>();
  private detached = false;

  constructor(opts: LockdownOptions) {
    this.opts = opts;
  }

  // ---------------------------------------------------------------- telemetry

  private elapsed(): number {
    return Math.max(0, Math.round((Date.now() - this.startedAt) / 1000));
  }

  /** Record an event, and optionally surface a warning to the learner. */
  private record(
    kind: ProctorEventKind,
    extra: Partial<ProctorEvent> = {},
    warning?: string,
  ) {
    if (this.events.length >= MAX_EVENTS) return;
    const event: ProctorEvent = {
      kind,
      at_seconds: this.elapsed(),
      question_id: extra.question_id ?? this.opts.currentQuestionId(),
      ...extra,
    };
    this.events.push(event);
    if (warning) this.opts.onWarn(warning, event);
  }

  /** The telemetry to send with the submission. */
  getEvents(): ProctorEvent[] {
    return [...this.events];
  }

  getElapsedSeconds(): number {
    return this.elapsed();
  }

  /** Count of events that reflect on the attempt, for the UI badge. */
  get warningCount(): number {
    return this.events.filter(
      (e) => e.kind !== 'tab_visible' && e.kind !== 'window_focus',
    ).length;
  }

  // ------------------------------------------------------------ burst checker

  /**
   * Check a written answer's length against how long ago we last saw it.
   *
   * Called whenever the answer text changes. Text that grows by a paragraph
   * between two ticks was not typed, and paste can arrive without a `paste`
   * event (drag-drop, IME, middle-click, a script) — so length-over-time is the
   * signal that survives, and the blocked-paste handler is only the polite half.
   */
  noteAnswerText(questionId: string, text: string) {
    const now = Date.now();
    const chars = text.length;
    const prev = this.lastLength.get(questionId);
    this.lastLength.set(questionId, { chars, at: now });
    if (!prev) return;

    const added = chars - prev.chars;
    const seconds = Math.max(0.001, (now - prev.at) / 1000);
    if (added >= BURST_MIN_CHARS && added / seconds > BURST_CHARS_PER_SECOND) {
      this.record(
        'answer_burst',
        { question_id: questionId, detail: `${added} characters appeared at once` },
        'That answer appeared all at once. Pasted answers are flagged for review.',
      );
    }
  }

  // -------------------------------------------------------------- attachment

  /** Wire up prevention + observation. Returns a detach function. */
  attach(): () => void {
    this.blockSelectionAndCopy();
    this.blockContextMenu();
    this.blockShortcuts();
    this.watchVisibility();
    this.watchFullscreen();
    this.watchMultiSession();
    return () => this.detach();
  }

  private on(
    target: Document | Window,
    type: string,
    handler: (e: any) => void,
  ) {
    target.addEventListener(type, handler);
    this.cleanups.push(() => target.removeEventListener(type, handler));
  }

  /**
   * Kill copy/cut/selection inside the exam.
   *
   * The `exam-locked` class does the visual half (no selection highlight, so
   * there is nothing to drag); the handlers catch the keyboard and menu routes.
   * Both are scoped to the exam so the rest of the app is untouched — and
   * critically, `input`/`textarea` stay selectable, because a candidate must be
   * able to edit their own written answer.
   */
  private blockSelectionAndCopy() {
    document.body.classList.add('exam-locked');
    this.cleanups.push(() => document.body.classList.remove('exam-locked'));

    const blockCopy = (e: ClipboardEvent) => {
      // Copying one's own typed answer is harmless; copying the paper is not.
      if (this.isOwnAnswerField(e.target)) return;
      e.preventDefault();
      this.record(
        'copy_attempt',
        { detail: e.type },
        'Copying the question paper is disabled during this test.',
      );
    };
    this.on(document, 'copy', blockCopy);
    this.on(document, 'cut', blockCopy);

    this.on(document, 'paste', (e: ClipboardEvent) => {
      const size = e.clipboardData?.getData('text')?.length ?? 0;
      e.preventDefault();
      this.record(
        'paste_attempt',
        { detail: size ? `pasted ${size} characters` : 'paste' },
        'Pasting into an answer is disabled during this test.',
      );
    });

    // Dragging text out of the paper is a copy by another name.
    this.on(document, 'dragstart', (e: DragEvent) => {
      if (this.isOwnAnswerField(e.target)) return;
      e.preventDefault();
    });
  }

  /** True for the learner's own answer box, where editing must keep working. */
  private isOwnAnswerField(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    if (!el || !el.tagName) return false;
    return el.tagName === 'TEXTAREA' || el.tagName === 'INPUT';
  }

  private blockContextMenu() {
    this.on(document, 'contextmenu', (e: MouseEvent) => {
      e.preventDefault();
      this.record(
        'context_menu',
        {},
        'The right-click menu is disabled during this test.',
      );
    });
  }

  /**
   * Block the keyboard routes to copying, printing and saving the paper.
   *
   * Ctrl/Cmd+C is not blocked here — the copy handler above already covers it
   * and can tell the answer field apart, which a keydown check cannot do as
   * reliably. What is blocked are the whole-page exfiltration routes.
   */
  private blockShortcuts() {
    this.on(document, 'keydown', (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();

      // F12 and Ctrl/Cmd+Shift+{I,J,C} — devtools.
      if (e.key === 'F12' || (mod && e.shiftKey && ['i', 'j', 'c'].includes(key))) {
        e.preventDefault();
        this.record(
          'devtools_open',
          { detail: e.key === 'F12' ? 'F12' : `Ctrl+Shift+${key.toUpperCase()}` },
          'Developer tools are not allowed during this test. This has been logged.',
        );
        return;
      }

      // Print, save, select-all, view-source.
      if (mod && ['p', 's', 'a', 'u'].includes(key)) {
        // Select-all inside your own answer is legitimate.
        if (key === 'a' && this.isOwnAnswerField(e.target)) return;
        e.preventDefault();
        this.record(
          'shortcut_blocked',
          { detail: `Ctrl+${key.toUpperCase()}` },
          'That shortcut is disabled during this test.',
        );
      }
    });
  }

  /**
   * Watch for the exam losing the screen.
   *
   * `visibilitychange` catches tab switches and minimising; `blur` catches focus
   * moving to another window that leaves this one visible. They overlap, so a
   * single "away" clock is shared and only the first of the pair opens it —
   * otherwise one alt-tab logs as two separate absences.
   */
  private watchVisibility() {
    const leave = (kind: 'tab_hidden' | 'window_blur') => {
      if (this.awaySince !== null) return;
      this.awaySince = Date.now();
      this.record(
        kind,
        {},
        'Leaving the exam is recorded. Stay on this tab until you submit.',
      );
    };

    const back = (kind: 'tab_visible' | 'window_focus') => {
      if (this.awaySince === null) return;
      const seconds = Math.round((Date.now() - this.awaySince) / 1000);
      this.awaySince = null;
      // Attach the duration to the departure event, which is what the server
      // scores; the return is logged plainly for the timeline.
      for (let i = this.events.length - 1; i >= 0; i -= 1) {
        const e = this.events[i];
        if (e.kind === 'tab_hidden' || e.kind === 'window_blur') {
          e.duration_seconds = seconds;
          break;
        }
      }
      this.record(kind, { duration_seconds: seconds });
    };

    this.on(document, 'visibilitychange', () => {
      if (document.hidden) leave('tab_hidden');
      else back('tab_visible');
    });
    this.on(window, 'blur', () => leave('window_blur'));
    this.on(window, 'focus', () => back('window_focus'));
  }

  private watchFullscreen() {
    this.on(document, 'fullscreenchange', () => {
      if (!document.fullscreenElement) {
        this.record('fullscreen_exit', {}, 'You left exam fullscreen.');
      }
    });
  }

  /**
   * Detect the same attempt open twice.
   *
   * A second tab is how someone reads the paper in one window while searching in
   * the other, and it looks innocent to every other check here. The exam claims
   * a key in localStorage; a second instance sees the claim, and both report it,
   * since we cannot tell which one is the "real" candidate.
   */
  private watchMultiSession() {
    const KEY = 'champ_exam_session';
    let existing: string | null = null;
    try {
      existing = localStorage.getItem(KEY);
    } catch {
      // Storage blocked (private window, hardened browser). Not a signal we can
      // collect, and not worth failing the exam over.
      return;
    }

    if (existing) {
      this.record(
        'multi_session',
        { detail: 'another exam tab was already open' },
        'This test is already open in another tab. Close the other one.',
      );
    }

    const token = `${this.startedAt}`;
    try {
      localStorage.setItem(KEY, token);
    } catch {
      return;
    }

    // A later tab overwrites the token; seeing that change means we are no
    // longer the only instance, so this tab reports it too.
    this.on(window, 'storage', (e: StorageEvent) => {
      if (e.key === KEY && e.newValue && e.newValue !== token) {
        this.record(
          'multi_session',
          { detail: 'the test was opened in a second tab' },
          'This test was just opened in another tab. That has been logged.',
        );
      }
    });

    this.cleanups.push(() => {
      try {
        if (localStorage.getItem(KEY) === token) localStorage.removeItem(KEY);
      } catch {
        /* nothing to clean up if storage is unavailable */
      }
    });
  }

  private detach() {
    if (this.detached) return;
    this.detached = true;
    for (const fn of this.cleanups.splice(0)) {
      try {
        fn();
      } catch {
        // A listener that won't detach must not stop the others from doing so.
      }
    }
  }
}
