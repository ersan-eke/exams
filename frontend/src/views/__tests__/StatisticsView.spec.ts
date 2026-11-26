import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { attempt, exam, sub, task } from '@/lib/__tests__/fixtures'
import type { StoredExam } from '@/types/attempt'
import StatisticsView from '../StatisticsView.vue'

const lib = vi.hoisted(() => ({ catalog: vi.fn() }))
vi.mock('@/stores/library', () => ({ useLibraryStore: () => lib }))
const subjectsLib = vi.hoisted(() => ({ listSubjects: vi.fn(), downloadAnki: vi.fn(), exportToNotion: vi.fn() }))
vi.mock('@/lib/subjects', () => subjectsLib)
const integrationsLib = vi.hoisted(() => ({ listIntegrations: vi.fn() }))
vi.mock('@/lib/integrations', () => integrationsLib)
const apiLib = vi.hoisted(() => ({ followJob: vi.fn() }))
vi.mock('@/lib/api', () => apiLib)

const stub = { template: '<div />' }
const stored = (id: string, title: string, p: Partial<StoredExam> = {}): StoredExam => ({
  id, title, structure: exam([task('t1', '1', [sub('a', 'a)', 4)])]), createdAt: 0, hasInk: false, ...p,
})
const done = (id: string, examId: string, startedAt: number) =>
  attempt({ id, examId, status: 'handed_in', startedAt, handedInAt: startedAt + 60_000, includedTaskIds: ['t1'] })

async function setup(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/statistics', name: 'statistics', component: StatisticsView },
      { path: '/statistics/:subject', name: 'statistics-subject', component: StatisticsView },
      { path: '/attempts/:attemptId/results', name: 'results', component: stub },
      { path: '/', name: 'new', component: stub },
    ],
  })
  router.push(path)
  await router.isReady()
  const wrapper = mount(StatisticsView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('StatisticsView', () => {
  beforeEach(() => {
    lib.catalog.mockReset().mockResolvedValue({
      exams: [stored('e1', 'GRNVS 2019'), stored('e2', 'GBS 2020'), stored('e3', 'IT 2020', { hidden: true })],
      attempts: [
        { ...done('a1', 'e1', 1000), gradedAt: 1, grades: { a: { main: 3 } } },
        done('a2', 'e2', 2000),
        done('a3', 'e3', 3000),
      ],
    })
  })

  it('first layer: subject buttons, totals, recent and activity, without hidden exams', async () => {
    const w = await setup('/statistics')
    expect(w.findAll('.subjects a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['GBS', '/statistics/GBS'],
      ['GRNVS', '/statistics/GRNVS'],
    ])
    expect(w.find('.stats').text()).toContain('2exams taken')
    expect(w.find('[data-section=points]').text()).toContain('75 %')
    expect(w.findAll('[data-section=recent] a').map((a) => a.text())).toEqual([
      expect.stringContaining('GBS 2020'),
      expect.stringContaining('GRNVS 2019'),
    ])
    expect(w.find('[data-group="4"]').text()).toContain('3 / 4 P')
    expect(w.find('[data-section=activity]').exists()).toBe(true)
    expect(w.text()).not.toContain('IT 2020')
  })

  it('second layer: one subject with its exams linking to their results', async () => {
    const w = await setup('/statistics/GRNVS')
    expect(w.find('h1').text()).toBe('GRNVS')
    expect(w.find('.stats').text()).toContain('1exams taken')
    const exams = w.findAll('[data-section=exams] a')
    expect(exams).toHaveLength(1)
    expect(exams[0]!.attributes('href')).toBe('/attempts/a1/results')
    expect(exams[0]!.text()).toContain('75 %')
    expect(w.find('[data-section=recent]').exists()).toBe(false)
  })

  describe('Anki export', () => {
    const button = (w: Awaited<ReturnType<typeof setup>>) =>
      w.findAll('button').find((b) => b.text() === 'Export weak questions to Anki')

    beforeEach(() => {
      subjectsLib.listSubjects.mockReset().mockResolvedValue([{ id: 's1', name: 'Grnvs' }])
      subjectsLib.downloadAnki.mockReset().mockResolvedValue(undefined)
    })

    it('downloads the deck of the subject found by name ignoring case', async () => {
      const w = await setup('/statistics/GRNVS')
      await button(w)!.trigger('click')
      await flushPromises()
      expect(subjectsLib.downloadAnki).toHaveBeenCalledWith('s1', 'GRNVS')
    })

    it('says when nothing scored below 60 %', async () => {
      subjectsLib.downloadAnki.mockRejectedValue(new Error('nothing_weak'))
      const w = await setup('/statistics/GRNVS')
      await button(w)!.trigger('click')
      await flushPromises()
      expect(w.find('[role=alert]').text()).toBe('No questions scored below 60% in this subject yet.')
    })

    it('is not on the all-subjects layer', async () => {
      expect(button(await setup('/statistics'))).toBeUndefined()
    })
  })

  describe('Notion export', () => {
    const button = (w: Awaited<ReturnType<typeof setup>>) =>
      w.findAll('button').find((b) => b.text() === 'Send weak questions to Notion' || b.text() === 'Sending…')
    const notion = (connections: object[], databaseUrl: string | null = null) =>
      integrationsLib.listIntegrations.mockResolvedValue({ notion: { enabled: true, connections, databaseUrl } })
    const acme = [{ id: 'n1', workspace: 'Acme', connectedAt: 1 }]

    beforeEach(() => {
      subjectsLib.listSubjects.mockReset().mockResolvedValue([{ id: 's1', name: 'Grnvs' }])
      subjectsLib.exportToNotion.mockReset().mockResolvedValue('j1')
      apiLib.followJob.mockReset().mockResolvedValue({ status: 'done', error_code: null })
      integrationsLib.listIntegrations.mockReset()
    })

    it('is absent when Notion is not connected', async () => {
      notion([])
      expect(button(await setup('/statistics/GRNVS'))).toBeUndefined()
    })

    it('reads Sending… and is disabled while the job runs', async () => {
      notion(acme)
      apiLib.followJob.mockReturnValue(new Promise(() => {}))
      const w = await setup('/statistics/GRNVS')
      await button(w)!.trigger('click')
      await flushPromises()
      expect(subjectsLib.exportToNotion).toHaveBeenCalledWith('s1')
      expect(button(w)!.text()).toBe('Sending…')
      expect(button(w)!.attributes('disabled')).toBeDefined()
    })

    it('links to the refreshed database on done', async () => {
      notion(acme)
      const w = await setup('/statistics/GRNVS')
      notion(acme, 'https://notion.so/db')
      await button(w)!.trigger('click')
      await flushPromises()
      const a = w.get('a[href="https://notion.so/db"]')
      expect(a.text()).toBe('Sent. Open in Notion')
    })

    it.each([
      ['nothing_weak', 'No questions scored below 60% in this subject yet.', 'post'],
      ['notion_not_connected', 'Reconnect Notion in Settings.', 'post'],
      ['notion_auth', 'Reconnect Notion in Settings.', 'job'],
      ['server', "Couldn't send to Notion. Try again.", 'job'],
    ])('shows the text for %s', async (code, text, where) => {
      notion(acme)
      if (where === 'post') subjectsLib.exportToNotion.mockRejectedValue(new Error(code))
      else apiLib.followJob.mockResolvedValue({ status: 'failed', error_code: code })
      const w = await setup('/statistics/GRNVS')
      await button(w)!.trigger('click')
      await flushPromises()
      expect(w.get('[role=alert]').text()).toBe(text)
      expect(button(w)!.attributes('disabled')).toBeUndefined()
    })
  })
})
