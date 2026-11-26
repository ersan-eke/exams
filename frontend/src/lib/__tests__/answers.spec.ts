import { describe, expect, it } from 'vitest'
import { emptyAnswer, isAnswered, migrateAnswer, sameAnswer } from '../answers'
import type { Answer } from '@/types/attempt'
import { ans } from './fixtures'

describe('answers', () => {
  it('emptyAnswer', () => {
    expect(emptyAnswer('draw')).toEqual(ans({ mode: 'draw' }))
  })
  it('isAnswered', () => {
    expect(isAnswered(undefined)).toBe(false)
    expect(isAnswered(ans({ text: '  \n' }))).toBe(false)
    expect(isAnswered(ans({ text: 'x' }))).toBe(true)
    expect(isAnswered(ans({ strokes: [{ points: [[0, 0]], erase: true }] }))).toBe(false)
    expect(isAnswered(ans({ strokes: [{ points: [[0, 0]], erase: false }] }))).toBe(true)
    expect(isAnswered(ans({ done: true }))).toBe(true)
    expect(isAnswered(ans({ ticks: [1] }))).toBe(true)
  })
  it('migrates single text/drawing answers to one part', () => {
    const old = { mode: 'draw', text: 'hi', strokes: [], done: false, ticks: [] } as unknown as Answer
    expect(migrateAnswer(old)).toEqual(ans({ mode: 'draw', text: 'hi' }))
    const blank = { mode: 'type', text: '', strokes: [], done: true, ticks: [] } as unknown as Answer
    expect(migrateAnswer(blank)).toEqual(ans({ done: true }))
    expect(migrateAnswer(ans({ text: 'new' }))).toEqual(ans({ text: 'new' }))
  })
  it('sameAnswer treats a missing part as empty', () => {
    expect(sameAnswer(ans(), ans({ text: '' }))).toBe(true)
    expect(sameAnswer(ans({ text: 'a' }), ans({ parts: [{ text: 'a', strokes: [] }, { text: 'b', strokes: [] }] }))).toBe(false)
  })
  it('sameAnswer', () => {
    expect(sameAnswer(undefined, ans())).toBe(true)
    expect(sameAnswer(undefined, undefined)).toBe(true)
    expect(sameAnswer(ans({ text: 'a' }), ans({ text: 'a' }))).toBe(true)
    expect(sameAnswer(ans({ text: 'a' }), ans({ text: 'b' }))).toBe(false)
    expect(sameAnswer(undefined, ans({ ticks: [0] }))).toBe(false)
  })
})
