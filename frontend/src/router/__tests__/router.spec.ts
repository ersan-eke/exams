import { describe, expect, it } from 'vitest'
import router from '../index'
import ComingSoonView from '@/views/ComingSoonView.vue'

describe('router', () => {
  it('resolves /practice to ComingSoonView with a title', () => {
    const r = router.resolve('/practice')
    expect(r.matched[0]!.components!.default).toBe(ComingSoonView)
    expect(r.meta.title).toBe('Practice')
  })

  it('marks the attempt route as focus mode', () => {
    const r = router.resolve('/attempts/x')
    expect(r.name).toBe('exam')
    expect(r.meta.focus).toBe(true)
  })

  it('names the core routes', () => {
    expect(router.resolve('/').name).toBe('new')
    expect(router.resolve('/exams/e1/settings').name).toBe('exam-settings')
    expect(router.resolve('/attempts/a/results').name).toBe('results')
    expect(router.resolve('/attempts/a/grade/self').name).toBe('grade')
    expect(router.resolve('/attempts/a/grade/solution').name).toBe('grade')
    expect(router.resolve('/exams/e1/view').name).toBe('exam-view')
    expect(router.resolve('/my-exams').name).toBe('my-exams')
    expect(router.resolve('/statistics').name).toBe('statistics')
    expect(router.resolve('/statistics/GRNVS').params.subject).toBe('GRNVS')
  })
})
