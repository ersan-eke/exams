import { describe, expect, it } from 'vitest'
import { elapsed, formatClock, formatOvertime, isOvertime, remaining } from '../clock'
import { attempt } from './fixtures'

describe('clock', () => {
  it('formats', () => {
    expect(formatClock(4_360_000)).toBe('1:12:40')
    expect(formatClock(760_000)).toBe('12:40')
    expect(formatOvertime(252_000)).toBe('+4:12')
  })
  it('elapsed while running and after hand-in', () => {
    const a = attempt()
    expect(elapsed(a, 4000)).toBe(3000)
    expect(elapsed(attempt({ handedInAt: 2500 }), 99_999)).toBe(1500)
  })
  it('overtime and remaining', () => {
    const a = attempt()
    expect(isOvertime(a, 10_999)).toBe(false)
    expect(isOvertime(a, 11_000)).toBe(true)
    expect(remaining(a, 4000)).toBe(7000)
    expect(remaining(a, 50_000)).toBe(0)
  })
})
