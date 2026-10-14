// Inline SVG icons for the course canvas and player. Static strings, rendered
// with {@html}; they never contain user content. Like Icon.svelte they are
// "live": class="icon" plus lv-* parts that the Live icons block in app.css
// animates (looping when standalone, on hover inside buttons and links).
const svg = (d: string, fill = false) =>
  `<svg class="icon" viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" fill="${fill ? 'currentColor' : 'none'}" stroke="${fill ? 'none' : 'currentColor'}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;

export const icons = {
  video: svg('<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5l5-3v9l-5-3z"/><circle class="lv-rec" cx="6.5" cy="9.5" r="1" fill="currentColor" stroke="none" opacity="0"/>'),
  quiz: svg('<path class="lv-twinkle" d="M11 3l1.7 4.3L17 9l-4.3 1.7L11 15l-1.7-4.3L5 9l4.3-1.7z"/><path class="lv-twinkle lv-d2" d="M18 14l.9 2.1L21 17l-2.1.9L18 20l-.9-2.1L15 17l2.1-.9z"/>'),
  test: svg('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path class="lv-draw" pathLength="1" d="M8.5 12.5l2 2 4-4.5"/><path class="lv-draw lv-d2" pathLength="1" d="M8.5 17.5h7"/>'),
  notes: svg('<path d="M6 3h9l4 4v14H6z"/><path d="M14.5 3v4.5H19"/><path class="lv-draw" pathLength="1" d="M9 12h7"/><path class="lv-draw lv-d2" pathLength="1" d="M9 16h5"/>'),
  play: svg('<path class="lv-pulse" d="M8 5.5v13l10.5-6.5z"/>', true),
  lock: svg('<rect x="5" y="11" width="14" height="10" rx="2"/><path class="lv-lift" d="M8 11V8a4 4 0 018 0v3"/>'),
  check: svg('<path class="lv-draw" pathLength="1" d="M5 12.5l4.5 4.5L19 7.5"/>'),
  expand: svg('<path class="lv-pulse" d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
  shrink: svg('<path class="lv-squish" d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>'),
  plus: svg('<path class="lv-quarter" d="M12 5v14M5 12h14"/>'),
  upload: svg('<path class="lv-lift" d="M12 15V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v5h16v-5"/>'),
  grip: svg('<path class="lv-squish" d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01" stroke-width="3.2"/>'),
  x: svg('<path class="lv-quarter" d="M6 6l12 12M18 6L6 18"/>'),
  sparkle: svg('<path class="lv-twinkle" d="M12 4l1.6 4.4L18 10l-4.4 1.6L12 16l-1.6-4.4L6 10l4.4-1.6z"/>'),
  panel: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><path class="lv-slide-r" d="M9 4v16"/>'),
  back: svg('<path class="lv-left" d="M15 5l-7 7 7 7"/>'),
  next: svg('<path class="lv-right" d="M9 5l7 7-7 7"/>'),
  key: svg('<g class="lv-wobble"><circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2.5 2.5M14 9l2 2"/></g>'),
  eye: svg('<g class="lv-blinkeye"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle class="lv-look" cx="12" cy="12" r="3"/></g>'),
  clock: svg('<circle cx="12" cy="12" r="8.5"/><path class="lv-hand" d="M12 7.5V12l3 2"/>'),
  shield: svg('<path class="lv-pulse" d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>'),
  file: svg('<g class="lv-wobble"><path d="M6 3h9l4 4v14H6z"/><path d="M14.5 3v4.5H19"/></g>'),
  qna: svg('<path d="M4 5.5h16v10.5H10l-4.5 3.5V16H4z"/><path class="lv-bob" d="M10 9a2 2 0 113 1.7c-.6.4-1 .8-1 1.5M12 14h.01"/>'),
  cc: svg('<rect x="3" y="5" width="18" height="14" rx="2.5"/><path class="lv-blink" d="M10.5 10.2a2.2 2.2 0 100 3.6M17 10.2a2.2 2.2 0 100 3.6"/>'),
  bell: svg('<path class="lv-bell" d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15z"/><path class="lv-clapper" d="M10 20.5a2 2 0 004 0"/>'),
};

export const kindLabel: Record<string, string> = {
  video: 'Episode', quiz: 'AI quiz', test: 'Test', notes: 'Notes',
};
