import { reactive, toRefs, watch } from 'vue'
import { defineStore } from 'pinia'
import type { AnswerMode, Provider } from '@/types/attempt'

const KEY = 'examen.settings'

interface Settings {
  defaultAnswerMode: AnswerMode
  attendanceDefault: boolean
  provider: Provider
  keys: Record<Provider, string>
  models: Record<Provider, string>
}

const PROVIDERS: Provider[] = ['anthropic', 'google', 'openrouter']
/** the server's defaults */
const MODELS: Record<Provider, string> = {
  anthropic: 'claude-sonnet-5-5',
  google: 'gemini-flash-latest',
  openrouter: 'google/gemini-2.5-flash',
}

const MODEL_OPTIONS = {
  anthropic: ['claude-sonnet-5-5', 'claude-haiku-5-5'],
  google: ['gemini-flash-latest', 'gemini-pro-latest'],
}

function load(): Settings {
  const defaults: Settings = {
    defaultAnswerMode: 'type',
    attendanceDefault: true,
    provider: 'anthropic',
    keys: { anthropic: '', google: '', openrouter: '' },
    models: { ...MODELS },
  }
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const s: Settings = { ...defaults, ...JSON.parse(raw) }
      if (s.defaultAnswerMode !== 'draw') s.defaultAnswerMode = 'type' // 'paper' was removed
      if (!PROVIDERS.includes(s.provider)) s.provider = defaults.provider
      s.keys = { ...defaults.keys, ...s.keys }
      s.models = { ...defaults.models, ...s.models }
      // unknown stored models of the fixed-list providers fall back to the default
      for (const p of ['anthropic', 'google'] as const)
        if (!MODEL_OPTIONS[p].includes(s.models[p])) s.models[p] = defaults.models[p]
      return s
    }
  } catch {
    // unreadable storage: fall back to defaults
  }
  return defaults
}

export const useSettingsStore = defineStore('settings', () => {
  const state = reactive<Settings>(load())
  watch(state, (v) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(v))
    } catch {
      // storage unavailable: keep in memory only
    }
  })
  return { ...toRefs(state) }
})
