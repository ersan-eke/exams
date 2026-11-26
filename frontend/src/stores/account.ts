import { ref } from 'vue'
import { defineStore } from 'pinia'
import { markAllDirty } from '@/lib/db'
import { sync } from '@/lib/sync'

export interface AccountUser {
  id: string
  name: string | null
  email: string | null
}

/** optional sign-in; without it everything stays on this device */
export const useAccountStore = defineStore('account', () => {
  const user = ref<AccountUser | null>(null)
  /** login providers the server has credentials for */
  const providers = ref<string[]>([])
  /** the OAuth callback sent us back with ?login=failed */
  const loginFailed = ref(false)
  /** ...or with ?login=denied: signed in fine, but the account isn't on the invite list */
  const loginDenied = ref(false)

  async function load(): Promise<void> {
    const url = new URL(location.href)
    if (url.searchParams.has('login')) {
      loginFailed.value = url.searchParams.get('login') === 'failed'
      loginDenied.value = url.searchParams.get('login') === 'denied'
      url.searchParams.delete('login')
      history.replaceState(history.state, '', url)
    }
    try {
      const res = await fetch('/api/me')
      if (!res.ok) return
      const body = await res.json()
      user.value = body.user
      providers.value = body.providers
      if (user.value) {
        // shortcut: a second account on this browser gets the first one's local data pushed into it; keep local data per account when shared browsers matter
        if (localStorage.getItem('sync-user') !== user.value.id) {
          await markAllDirty()
          localStorage.removeItem('sync-cursor')
          localStorage.setItem('sync-user', user.value.id)
        }
        void sync()
      }
    } catch {
      // offline or no backend: stay signed out
    }
  }

  async function logout(): Promise<void> {
    const res = await fetch('/api/auth/logout', { method: 'POST' })
    if (res.ok) user.value = null
  }

  return { user, providers, loginFailed, loginDenied, load, logout }
})
