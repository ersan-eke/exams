import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAccountStore } from '@/stores/account'
import AddMaterial from '../AddMaterial.vue'

const conflict = (subject: string | null) =>
  new Response(JSON.stringify({ detail: { code: 'already_uploaded', document_id: 'd1', subject } }), { status: 409 })

async function drop(reply: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply))
  setActivePinia(createPinia())
  useAccountStore().user = { id: 'u1' } as never
  const router = createRouter({ history: createMemoryHistory(), routes: [{ name: 'material', path: '/material/:id', component: { template: '<div />' } }] })
  const w = mount(AddMaterial, { props: { subject: 'Algebra' }, global: { plugins: [router] } })
  const input = w.find('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [new File(['%PDF-'], 'a.pdf')], configurable: true })
  await input.trigger('change')
  await flushPromises()
  return w
}

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => vi.unstubAllGlobals())

describe('AddMaterial', () => {
  it('says which Subject already has the file and links to that Deck', async () => {
    const w = await drop(conflict('Numerik'))
    expect(w.find('[role=alert]').text()).toContain('Already in Numerik')
    expect(w.find('[role=alert] a').attributes('href')).toBe('/material/d1')
  })

  it('names no Subject for an unfiled Deck', async () => {
    const w = await drop(conflict(null))
    expect(w.find('[role=alert]').text()).toContain('Already uploaded')
    expect(w.find('[role=alert] a').attributes('href')).toBe('/material/d1')
  })
})
