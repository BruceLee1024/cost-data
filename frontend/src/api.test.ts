import { describe, expect, it } from 'vitest'
import { formatAmount } from './api'

describe('formatAmount', () => {
  it('formats decimal strings without changing business truth', () => {
    expect(formatAmount({ value: '12345.6789', scale: 6 })).toBe('12,345.6789')
    expect(formatAmount({ value: null, scale: 6 })).toBe('—')
  })
})
