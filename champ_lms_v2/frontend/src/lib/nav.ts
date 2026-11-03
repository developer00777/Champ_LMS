// The app's main navigation, shared by the top bar and drawer in the root
// layout and by the video studio's app menu (the studio covers the top bar).
export type NavItem = { href: string; label: string; icon: string; match: (p: string) => boolean; admin?: boolean };

export const NAV: NavItem[] = [
  { href: '/', label: 'Home', icon: 'home', match: (p) => p === '/' },
  { href: '/my-learning', label: 'My Learning', icon: 'book', match: (p) => p === '/my-learning' },
  { href: '/paths', label: 'Paths', icon: 'route', match: (p) => p === '/paths' },
  { href: '/daily', label: 'Today', icon: 'flame', match: (p) => p === '/daily' },
  { href: '/challenges', label: 'Challenges', icon: 'flag', match: (p) => p === '/challenges' },
  { href: '/tests', label: 'Tests', icon: 'clipboard', match: (p) => p.startsWith('/tests') },
  { href: '/leaderboard', label: 'Leaderboard', icon: 'trophy', match: (p) => p === '/leaderboard' },
  { href: '/admin', label: 'Admin', icon: 'settings', match: (p) => p.startsWith('/admin'), admin: true },
];
