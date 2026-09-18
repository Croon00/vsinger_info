// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ScrollMore from './ScrollMore.vue'

afterEach(() => vi.unstubAllGlobals())

it('requests more when the sentinel enters view and stops at the end', async () => {
  let notify: IntersectionObserverCallback = () => {}
  const disconnect = vi.fn()
  vi.stubGlobal('IntersectionObserver', class {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = disconnect
    constructor(callback: IntersectionObserverCallback) { notify = callback }
  })
  const wrapper = mount(ScrollMore, { props: { shown: 20, total: 45 }, global: { stubs: { UButton: { template: '<button><slot /></button>' } } } })
  notify([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
  expect(wrapper.emitted('more')).toHaveLength(1)
  await wrapper.find('button').trigger('click')
  expect(wrapper.emitted('more')).toHaveLength(2)
  await wrapper.setProps({ shown: 60 })
  notify([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
  expect(wrapper.emitted('more')).toHaveLength(2)
  expect(wrapper.find('button').exists()).toBe(false)
  expect(wrapper.text()).toContain('45 / 45')
  wrapper.unmount()
  expect(disconnect).toHaveBeenCalled()
})
