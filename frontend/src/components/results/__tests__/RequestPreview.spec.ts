import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { GradeRequest } from '@/lib/grading'
import { GradeError } from '@/lib/grading'
import RequestPreview from '../RequestPreview.vue'

const request: GradeRequest = {
  provider: 'google',
  model: 'gemini-flash-latest',
  points: 2,
  question: { text: 'Aufgabe 3 · b)\n\nFind the two errors.', images: ['QQ'] },
  solution: { text: 'f[n-1] is wrong', images: ['SS'], rubric: [{ item: 'finds error 1', max: 1, source: 'solution' }] },
  references: [],
  answer: { text: '', images: ['AA'] },
}

const open = async (build: () => Promise<GradeRequest | null>) => {
  const w = mount(RequestPreview, { props: { build }, attachTo: document.body })
  await w.find('button').trigger('click')
  await flushPromises()
  return w
}

describe('RequestPreview', () => {
  it('shows every part of the request with its images', async () => {
    const w = await open(async () => request)
    const text = document.body.textContent!
    expect(text).toContain('Find the two errors.')
    expect(text).toContain('f[n-1] is wrong')
    expect(text).toContain('finds error 1')
    expect(text).toContain('gemini-flash-latest')
    expect(text).toContain('Max points: 2')
    const srcs = [...document.body.querySelectorAll('img')].map((i) => i.getAttribute('src'))
    expect(srcs).toEqual(['data:image/png;base64,QQ', 'data:image/png;base64,SS', 'data:image/png;base64,AA'])
    w.unmount()
  })

  it('says when the subtask is not sent', async () => {
    const w = await open(async () => null)
    expect(document.body.textContent).toContain('not sent to the model')
    w.unmount()
  })

  it('shows a build error instead of the request', async () => {
    const w = await open(async () => {
      throw new GradeError('too_many_images')
    })
    expect(document.body.textContent).toContain('too many images')
    w.unmount()
  })

  it('builds only when opened', () => {
    const build = vi.fn(async () => request)
    mount(RequestPreview, { props: { build } })
    expect(build).not.toHaveBeenCalled()
  })
})
