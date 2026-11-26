import type { Attempt } from '@/types/attempt'

export function elapsed(a: Attempt, now: number): number {
  return (a.handedInAt ?? now) - a.startedAt
}

export function isOvertime(a: Attempt, now: number): boolean {
  return elapsed(a, now) >= a.timeLimitMs
}

export function remaining(a: Attempt, now: number): number {
  return Math.max(0, a.timeLimitMs - elapsed(a, now))
}

const pad = (n: number) => String(n).padStart(2, '0')

function hms(ms: number): { h: number; m: number; s: number } {
  const total = Math.floor(Math.max(0, ms) / 1000)
  return { h: Math.floor(total / 3600), m: Math.floor((total % 3600) / 60), s: total % 60 }
}

export function formatClock(ms: number): string {
  const { h, m, s } = hms(ms)
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

export function formatOvertime(ms: number): string {
  const { h, m, s } = hms(ms)
  return h > 0 ? `+${h}:${pad(m)}:${pad(s)}` : `+${m}:${pad(s)}`
}
