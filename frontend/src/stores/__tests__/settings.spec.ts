import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '../settings'

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('has defaults', () => {
    const s = useSettingsStore()
    expect(s.defaultAnswerMode).toBe('type')
    expect(s.attendanceDefault).toBe(true)
  })

  it('persists changes', async () => {
    const s = useSettingsStore()
    s.defaultAnswerMode = 'draw'
    await nextTick()
    expect(JSON.parse(localStorage.getItem('examen.settings')!).defaultAnswerMode).toBe('draw')
  })

  it('has provider defaults', () => {
    const s = useSettingsStore()
    expect(s.provider).toBe('anthropic')
    expect(s.keys).toEqual({ anthropic: '', google: '', openrouter: '' })
    expect(s.models).toEqual({
      anthropic: 'claude-sonnet-5-5',
      google: 'gemini-flash-latest',
      openrouter: 'google/gemini-2.5-flash',
    })
  })

  it('persists keys and models', async () => {
    const s = useSettingsStore()
    s.keys.google = 'k'
    s.models.openrouter = 'x/y'
    await nextTick()
    const stored = JSON.parse(localStorage.getItem('examen.settings')!)
    expect(stored.keys.google).toBe('k')
    expect(stored.models.openrouter).toBe('x/y')
  })

  it('falls back for an unknown provider and missing entries', () => {
    localStorage.setItem(
      'examen.settings',
      JSON.stringify({ provider: 'nope', keys: { google: 'g' }, models: { anthropic: 'm', google: 'gemini-pro-latest', openrouter: 'x/y' } }),
    )
    const s = useSettingsStore()
    expect(s.provider).toBe('anthropic')
    expect(s.keys).toEqual({ anthropic: '', google: 'g', openrouter: '' })
    expect(s.models.anthropic).toBe('claude-sonnet-5-5') // unknown stored model
    expect(s.models.google).toBe('gemini-pro-latest') // known one is kept
    expect(s.models.openrouter).toBe('x/y')
  })
})
