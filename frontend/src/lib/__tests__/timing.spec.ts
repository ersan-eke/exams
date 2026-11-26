import { describe, expect, it } from 'vitest'
import { addTime } from '../timing'

describe('addTime', () => {
  it('splits evenly into main', () => {
    expect(addTime({}, ['A2b', 'A2c'], 1000, false)).toEqual({
      A2b: { main: 500, over: 0 }, A2c: { main: 500, over: 0 },
    })
  })
  it('adds to over in overtime and does not mutate', () => {
    const t = { A: { main: 5, over: 1 } }
    expect(addTime(t, ['A'], 100, true)).toEqual({ A: { main: 5, over: 101 } })
    expect(t).toEqual({ A: { main: 5, over: 1 } })
  })
  it('no-op for empty openIds', () => {
    const t = { A: { main: 5, over: 1 } }
    expect(addTime(t, [], 100, false)).toEqual(t)
  })
})
