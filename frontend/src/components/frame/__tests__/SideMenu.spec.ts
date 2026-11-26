import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SideMenu from '../SideMenu.vue'

function make() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/my-exams', '/statistics', '/practice', '/quizzes', '/ask'].map((path) => ({
      path,
      component: { template: '<div />' },
    })),
  })
  return mount(SideMenu, { global: { plugins: [router] } })
}

describe('SideMenu', () => {
  beforeEach(() => localStorage.clear())

  it('renders the six entries in order', () => {
    const w = make()
    expect(w.findAll('a').map((a) => a.text())).toEqual([
      'New exam',
      'My exams',
      'Statistics',
      'Practice',
      'Quizzes',
      'Ask',
    ])
  })

  it('collapses, hides labels and persists', async () => {
    const w = make()
    await w.get('button.toggle').trigger('click')
    expect(w.classes()).toContain('collapsed')
    expect(w.text()).not.toContain('New exam')
    expect(localStorage.getItem('examen.menuCollapsed')).toBe('1')
  })

  it('restores the collapsed state from storage', () => {
    localStorage.setItem('examen.menuCollapsed', '1')
    expect(make().classes()).toContain('collapsed')
  })

  describe('on a narrow screen', () => {
    beforeEach(() => {
      vi.stubGlobal('matchMedia', (q: string) => ({
        matches: q.includes('max-width'),
        addEventListener: () => {},
        removeEventListener: () => {},
      }))
    })
    afterEach(() => vi.unstubAllGlobals())

    it('starts as a rail and expands as an overlay without touching the stored preference', async () => {
      localStorage.setItem('examen.menuCollapsed', '0')
      const w = make()
      expect(w.classes()).toContain('collapsed')
      expect(w.classes()).toContain('narrow')
      await w.get('button.toggle').trigger('click')
      expect(w.classes()).not.toContain('collapsed')
      expect(localStorage.getItem('examen.menuCollapsed')).toBe('0')
    })
  })
})
