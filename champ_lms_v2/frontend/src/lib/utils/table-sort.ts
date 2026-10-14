// Three-state column sorting for admin tables: default (the order the data
// arrived in) → ascending → descending → back to default.

export type SortDir = 'none' | 'asc' | 'desc';
export interface SortState { key: string | null; dir: SortDir }

export const NO_SORT: SortState = { key: null, dir: 'none' };

type SortValue = string | number | boolean | Date | null | undefined;
export type SortAccessors<T> = Record<string, (row: T) => SortValue>;

/** The next state after clicking `key`'s header. A new column starts at ascending. */
export function cycleSort(s: SortState | undefined, key: string): SortState {
  if (!s || s.key !== key || s.dir === 'none') return { key, dir: 'asc' };
  if (s.dir === 'asc') return { key, dir: 'desc' };
  return NO_SORT;
}

export function dirFor(s: SortState | undefined, key: string): SortDir {
  return s && s.key === key ? s.dir : 'none';
}

export function ariaSort(s: SortState | undefined, key: string): 'ascending' | 'descending' | 'none' {
  const d = dirFor(s, key);
  return d === 'asc' ? 'ascending' : d === 'desc' ? 'descending' : 'none';
}

// Numeric-aware and case-insensitive, so "CHMP-2" sorts before "CHMP-10".
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

const isBlank = (v: SortValue) =>
  v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v)) ||
  (v instanceof Date && Number.isNaN(v.getTime()));

function compare(a: Exclude<SortValue, null | undefined>, b: Exclude<SortValue, null | undefined>): number {
  const x = a instanceof Date ? a.getTime() : typeof a === 'boolean' ? Number(a) : a;
  const y = b instanceof Date ? b.getTime() : typeof b === 'boolean' ? Number(b) : b;
  if (typeof x === 'number' && typeof y === 'number') return x - y;
  return collator.compare(String(x), String(y));
}

/**
 * A sorted copy of `rows` (the input is never mutated, so "default" is always
 * the original order). Blank values sit at the bottom in both directions, and
 * ties keep their original order.
 */
export function sortRows<T>(rows: T[], s: SortState | undefined, accessors: SortAccessors<T>): T[] {
  const get = s && s.dir !== 'none' && s.key ? accessors[s.key] : undefined;
  if (!get) return rows;
  const sign = s!.dir === 'asc' ? 1 : -1;
  return rows
    .map((row, i) => ({ row, i, v: get(row) }))
    .sort((a, b) => {
      const ab = isBlank(a.v), bb = isBlank(b.v);
      if (ab || bb) return ab === bb ? a.i - b.i : ab ? 1 : -1;
      return sign * compare(a.v!, b.v!) || a.i - b.i;
    })
    .map((x) => x.row);
}
