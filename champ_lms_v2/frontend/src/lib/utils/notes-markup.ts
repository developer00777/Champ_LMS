/**
 * The light markup used for course notes: "## " starts a heading, "- " (or
 * "• " / "* ") starts a bullet, anything else is a paragraph. Parsed into
 * blocks so it renders as plain text nodes, never as HTML.
 */
export type NoteBlock =
  | { type: 'h'; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] };

export function parseNotes(source: string | null | undefined): NoteBlock[] {
  const blocks: NoteBlock[] = [];
  let list: string[] | null = null;
  for (const raw of (source ?? '').split('\n')) {
    const line = raw.trim();
    const bullet = line.match(/^(?:[-*•])\s+(.*)$/);
    if (bullet) {
      if (!list) { list = []; blocks.push({ type: 'ul', items: list }); }
      list.push(bullet[1]);
      continue;
    }
    list = null;
    if (!line) continue;
    if (line.startsWith('## ') || line.startsWith('# ')) blocks.push({ type: 'h', text: line.replace(/^#+\s+/, '') });
    else blocks.push({ type: 'p', text: line });
  }
  return blocks;
}
