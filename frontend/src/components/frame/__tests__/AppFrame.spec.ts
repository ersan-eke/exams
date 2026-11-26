import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppFrame from '../AppFrame.vue'
import { useAccountStore } from '@/stores/account'

async function openAccount() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  const w = mount(AppFrame, { global: { plugins: [router] } })
  await w.get('[aria-label="Account"]').trigger('click')
  return w.get('.pop')
}

describe('AppFrame account popover', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('offers a sign-in link per configured provider', async () => {
    useAccountStore().providers = ['github', 'google']
    const links = (await openAccount()).findAll('a')
    expect(links.map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['GitHub', '/api/auth/github/login'],
      ['Google', '/api/auth/google/login'],
    ])
  })

  it('shows who is signed in and a sign-out button', async () => {
    useAccountStore().user = { id: 'u1', name: 'Ada', email: null }
    const pop = await openAccount()
    expect(pop.text()).toContain('Signed in as Ada')
    expect(pop.get('button').text()).toBe('Sign out')
  })

  it('says so when the server has no providers', async () => {
    expect((await openAccount()).text()).toBe("Sign-in isn't set up on this server")
  })
})
