// The app's own confirm / alert dialogs, in place of the browser's
// confirm() and alert(): themed, light and dark, and they don't freeze the
// page. DialogHost (in the root layout) shows them one at a time.
//
//   if (!(await confirmDialog({ title: 'Delete this question?', confirm: 'Delete', danger: true }))) return;
//   const choice = await openDialog({ title, actions: [...] });   // an action's id, or null if dismissed
import { writable } from 'svelte/store';

export type DialogAction = { id: string; label: string; kind?: 'primary' | 'danger' | 'ghost'; disabled?: boolean };
export type DialogIcon = 'alert' | 'trash' | 'info' | 'unsaved';
export type DialogOptions = {
  title: string;
  message?: string;
  icon?: DialogIcon;
  tone?: 'danger' | 'warn' | 'info';
  /** Left to right; the last is the main one. */
  actions: DialogAction[];
  /** The action focused on open: the safe one for anything destructive. */
  focus?: string;
};
export type DialogRequest = DialogOptions & { resolve: (id: string | null) => void };

const queue = writable<DialogRequest[]>([]);
export const dialogs = { subscribe: queue.subscribe };

/** Resolves with the chosen action's id, or null when dismissed (Esc, the backdrop). */
export function openDialog(opts: DialogOptions): Promise<string | null> {
  return new Promise(resolve => queue.update(q => [...q, { ...opts, resolve }]));
}

export function settleDialog(req: DialogRequest, id: string | null) {
  queue.update(q => q.filter(r => r !== req));
  req.resolve(id);
}

export async function confirmDialog(o: {
  title: string; message?: string; confirm?: string; cancel?: string; danger?: boolean; icon?: DialogIcon;
}): Promise<boolean> {
  const id = await openDialog({
    title: o.title,
    message: o.message,
    icon: o.icon ?? (o.danger ? 'trash' : 'info'),
    tone: o.danger ? 'danger' : 'info',
    actions: [
      { id: 'cancel', label: o.cancel ?? 'Cancel', kind: 'ghost' },
      { id: 'ok', label: o.confirm ?? 'OK', kind: o.danger ? 'danger' : 'primary' },
    ],
    focus: o.danger ? 'cancel' : 'ok',
  });
  return id === 'ok';
}

export async function alertDialog(o: { title: string; message?: string; ok?: string; tone?: 'danger' | 'warn' | 'info' }) {
  await openDialog({
    title: o.title,
    message: o.message,
    icon: o.tone === 'info' ? 'info' : 'alert',
    tone: o.tone ?? 'danger',
    actions: [{ id: 'ok', label: o.ok ?? 'OK', kind: 'primary' }],
    focus: 'ok',
  });
}
