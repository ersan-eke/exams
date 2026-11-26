import type { SubtaskTime } from '@/types/attempt'

export function addTime(
  time: Record<string, SubtaskTime>,
  openIds: string[],
  dtMs: number,
  overtime: boolean,
): Record<string, SubtaskTime> {
  if (openIds.length === 0) return time
  const share = dtMs / openIds.length
  const next = { ...time }
  for (const id of openIds) {
    const cur = next[id] ?? { main: 0, over: 0 }
    next[id] = overtime ? { main: cur.main, over: cur.over + share } : { main: cur.main + share, over: cur.over }
  }
  return next
}
