<script lang="ts" context="module">
  // One stroke-icon family for all UI chrome (24px grid, round caps).
  //
  // Every icon is "live": its lv-* parts are animated by the Live icons block
  // in app.css (standalone icons loop; icons inside links and buttons play
  // while hovered or focused). At rest each one draws exactly like a plain
  // icon; extras that only exist mid-animation sit at opacity 0.
  export const ICONS: Record<string, string> = {
    home: '<path class="lv-roof" d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/><rect class="lv-glow" x="10" y="15" width="4" height="6" fill="currentColor" stroke="none" opacity="0"/>',
    book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/><path class="lv-draw" pathLength="1" d="M8.5 7.5h7"/><path class="lv-draw lv-d2" pathLength="1" d="M8.5 11h4.5"/>',
    route: '<circle cx="6" cy="19" r="2.5"/><circle class="lv-ping" cx="18" cy="5" r="2.5"/><path d="M8.5 19h7a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7h7"/><path class="lv-trail" pathLength="1" d="M8.5 19h7a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7h7" stroke-width="3.2" opacity="0"/>',
    flame: '<path class="lv-outer" d="M12 22c4 0 7-2.8 7-7 0-4.5-3.5-7.5-5-11-1 3-3 4-4.5 5.5C8 11 7.5 9.5 7 8.5 5.7 10 5 12.4 5 15c0 4.2 3 7 7 7z"/><path class="lv-inner" d="M12 22c-1.7 0-3-1.3-3-3 0-2 1.5-3 3-5 1.5 2 3 3 3 5 0 1.7-1.3 3-3 3z"/><circle class="lv-ember" cx="16.5" cy="9" r="0.9" fill="currentColor" stroke="none" opacity="0"/>',
    flag: '<path d="M5 22V4"/><path class="lv-cloth" d="M5 4h12l-2 4 2 4H5"/>',
    clipboard: '<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V3h6v1"/><path class="lv-draw" pathLength="1" d="m9 13 2 2 4-4"/>',
    trophy: '<g class="lv-hop"><path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></g><path d="M8 21h8M12 17v4"/><path class="lv-spark" d="M12 5.5v3M10.5 7h3" opacity="0"/>',
    settings: '<g class="lv-spin"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></g>',
    star: '<path class="lv-twinkle" d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    zap: '<path class="lv-flash" d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    sun: '<circle class="lv-pulse" cx="12" cy="12" r="4"/><path class="lv-spin lv-slow" d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path class="lv-wobble" d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/><path class="lv-dot" d="M18 3.5v2M17 4.5h2" opacity="0"/>',
    logout: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><g class="lv-left"><path d="m10 17-5-5 5-5"/><path d="M5 12h12"/></g>',
    menu: '<path class="lv-draw" pathLength="1" d="M4 7h16"/><path class="lv-draw lv-d1" pathLength="1" d="M4 12h16"/><path class="lv-draw lv-d2" pathLength="1" d="M4 17h10"/>',
    close: '<path class="lv-quarter" d="M6 6l12 12M18 6 6 18"/>',
    play: '<path class="lv-pulse" d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.8l-12-7.5A1 1 0 0 0 7 4.5z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path class="lv-bob" d="M12 11v5M12 8h.01"/>',
    chevronLeft: '<path class="lv-left" d="m15 18-6-6 6-6"/>',
    chevronRight: '<path class="lv-right" d="m9 18 6-6-6-6"/>',
    arrowRight: '<path class="lv-right" d="M5 12h14M13 6l6 6-6 6"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle class="lv-pulse" cx="12" cy="12" r="5"/><circle class="lv-blink lv-d2" cx="12" cy="12" r="1"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path class="lv-bob" d="M8 3v4M16 3v4"/><circle class="lv-dot" cx="12" cy="15.5" r="1.3" fill="currentColor" stroke="none" opacity="0"/>',
    check: '<path class="lv-draw" pathLength="1" d="m5 12 5 5 9-10"/>',
    circle: '<circle class="lv-pulse" cx="12" cy="12" r="8"/>',
    alert: '<g class="lv-shake"><path d="M12 3 2 20h20z"/><path class="lv-blink" d="M12 10v4M12 17h.01"/></g>',
    film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16"/><path class="lv-blink" d="M3 9h4M17 9h4"/><path class="lv-blink lv-d2" d="M3 15h4M17 15h4"/>',
    search: '<g class="lv-scan"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></g>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path class="lv-draw" pathLength="1" d="m3 7 9 6 9-6"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path class="lv-lift" d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    eye: '<g class="lv-blinkeye"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle class="lv-look" cx="12" cy="12" r="3"/></g>',
    eyeOff: '<path class="lv-draw" pathLength="1" d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.6 9.6 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    award: '<g class="lv-wobble"><circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 8 5-3 5 3-1.5-8"/></g><path class="lv-spark" d="M12 7.5v3M10.5 9h3" opacity="0"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path class="lv-hand" d="M12 7v5l3 2"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path class="lv-hand lv-rev" d="M12 7v5l3 2"/>',
    user: '<circle class="lv-bob" cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    users: '<circle class="lv-bob" cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path class="lv-bob lv-d2" d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14a6.5 6.5 0 0 1 3.5 6"/>',
    shield: '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z"/><path class="lv-draw" pathLength="1" d="m9 12 2 2 4-4"/>',
    key: '<g class="lv-wobble"><circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M14 9l2 2"/></g>',
    unlock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path class="lv-lift" d="M8 11V7a4 4 0 0 1 7.5-2"/>',
    plus: '<path class="lv-quarter" d="M12 5v14M5 12h14"/>',
    minus: '<path class="lv-squeeze" d="M5 12h14"/>',
    edit: '<g class="lv-scribble"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></g>',
    trash: '<g class="lv-lid"><path d="M4 7h16"/><path d="M9 7V4h6v3"/></g><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
    upload: '<path class="lv-lift" d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    download: '<path class="lv-drop" d="M12 4v12M7 11l5 5 5-5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    video: '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="m16 10 6-3v10l-6-3"/><circle class="lv-rec" cx="5.5" cy="9.5" r="1" fill="currentColor" stroke="none" opacity="0"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path class="lv-draw" pathLength="1" d="M9 13h6"/><path class="lv-draw lv-d2" pathLength="1" d="M9 17h4"/>',
    folder: '<path class="lv-peek" d="M8 11V6.5h8V11" opacity="0"/><path class="lv-hop" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    layers: '<path class="lv-lift" d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    grid: '<rect class="lv-squish" x="3" y="3" width="7" height="7" rx="1.5"/><rect class="lv-squish lv-d1" x="14" y="3" width="7" height="7" rx="1.5"/><rect class="lv-squish lv-d3" x="3" y="14" width="7" height="7" rx="1.5"/><rect class="lv-squish lv-d2" x="14" y="14" width="7" height="7" rx="1.5"/>',
    list: '<path class="lv-draw" pathLength="1" d="M9 6h12"/><path class="lv-draw lv-d1" pathLength="1" d="M9 12h12"/><path class="lv-draw lv-d2" pathLength="1" d="M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    filter: '<path class="lv-squish" d="M3 5h18l-7 8v6l-4 2v-8z"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle class="lv-slide-l" cx="16" cy="6" r="2"/><circle class="lv-slide-r lv-d1" cx="10" cy="12" r="2"/><circle class="lv-slide-l lv-d2" cx="18" cy="18" r="2"/>',
    bell: '<path class="lv-bell" d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path class="lv-clapper" d="M10 21h4"/>',
    refresh: '<g class="lv-spin lv-fast"><path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 3v5h5M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 21v-5h-5"/></g>',
    copy: '<rect class="lv-se" x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    external: '<path class="lv-out" d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
    send: '<g class="lv-fly"><path d="M21 3 10 14"/><path d="m21 3-7 18-4-7-7-4z"/></g>',
    save: '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path class="lv-drop" d="M7 3v5h8"/><path d="M7 21v-7h10v7"/>',
    sparkles: '<path class="lv-pulse" d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path class="lv-twinkle" d="m12 8 1.5 2.5L16 12l-2.5 1.5L12 16l-1.5-2.5L8 12l2.5-1.5z"/>',
    chart: '<path d="M22 20H2"/><path class="lv-bar" d="M4 20V10"/><path class="lv-bar lv-d1" d="M10 20V4"/><path class="lv-bar lv-d2" d="M16 20v-7"/>',
    trend: '<path class="lv-draw" pathLength="1" d="m3 17 6-6 4 4 8-8"/><path class="lv-out" d="M15 7h6v6"/>',
    mic: '<rect class="lv-pulse" x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    message: '<path d="M4 5h16v11H9l-5 4z"/><g stroke-width="2.6"><path class="lv-typing" d="M9 10.5h.01" opacity="0"/><path class="lv-typing lv-d1" d="M12 10.5h.01" opacity="0"/><path class="lv-typing lv-d2" d="M15 10.5h.01" opacity="0"/></g>',
    heart: '<path class="lv-beat" d="M12 20s-7.5-4.6-9-9.3C1.9 7.2 4.3 4 7.6 4c2 0 3.4 1.2 4.4 2.6C13 5.2 14.4 4 16.4 4c3.3 0 5.7 3.2 4.6 6.7-1.5 4.7-9 9.3-9 9.3z"/>',
    gift: '<g class="lv-lid"><rect x="3" y="8" width="18" height="5" rx="1"/><path d="M12 8v5"/><path d="M12 8C9 8 7.5 6.5 8 5s3 0 4 3c1-3 3.5-4.5 4-3s-1 3-4 3z"/></g><path d="M5 13v7h14v-7M12 13v7"/>',
    xCircle: '<circle cx="12" cy="12" r="9"/><path class="lv-quarter" d="m9 9 6 6M15 9l-6 6"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path class="lv-draw" pathLength="1" d="m8 12 3 3 5-6"/>',
    chevronDown: '<path class="lv-drop" d="m6 9 6 6 6-6"/>',
    chevronUp: '<path class="lv-lift" d="m18 15-6-6-6 6"/>',
    arrowLeft: '<path class="lv-left" d="M19 12H5M11 18l-6-6 6-6"/>',
    more: '<circle class="lv-bob" cx="5" cy="12" r="1"/><circle class="lv-bob lv-d1" cx="12" cy="12" r="1"/><circle class="lv-bob lv-d2" cx="19" cy="12" r="1"/>',
    link: '<path class="lv-out" d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path class="lv-in" d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    pause: '<path class="lv-bar" d="M8 5v14"/><path class="lv-bar lv-d2" d="M16 5v14"/>',
    hash: '<path class="lv-wobble" d="M5 9h15M4 15h15M10 3 8 21M16 3l-2 18"/>',
    medal: '<g class="lv-swing"><circle cx="12" cy="15" r="6"/><path d="M8.5 10 5 3h5l2 4 2-4h5l-3.5 7"/></g>',
    building: '<path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M2 21h20"/><path class="lv-blink" d="M8 7h4"/><path class="lv-blink lv-d1" d="M8 11h4"/><path class="lv-blink lv-d2" d="M8 15h4"/>',
  };
</script>

<script lang="ts">
  export let name: keyof typeof ICONS | string;
  export let size = 20;
  export let stroke = 1.75;
  /** Accessible label; omit for decorative icons. */
  export let label: string | undefined = undefined;
</script>

<svg
  class="icon"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  role={label ? 'img' : undefined}
  aria-label={label}
  aria-hidden={label ? undefined : 'true'}
>{@html ICONS[name] ?? ''}</svg>

<style>
  .icon { flex-shrink: 0; display: block; }
</style>
