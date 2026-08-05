import { describe, expect, it } from 'vitest'
import { MESSAGES, RULE_PAGES, t } from './strings'

const RULE_PAGE_COUNT = 5 // screens.md: rule_dialog の page_count

describe('i18n strings', () => {
  it('日英でキー集合が一致する', () => {
    expect(Object.keys(MESSAGES.ja).sort()).toEqual(Object.keys(MESSAGES.en).sort())
  })

  it('全文言が空文字でない', () => {
    for (const lang of ['ja', 'en'] as const) {
      for (const [key, value] of Object.entries(MESSAGES[lang])) {
        expect(value, `${lang}.${key}`).not.toBe('')
      }
    }
  })

  it('ルールページは両言語とも5ページで、タイトル・本文が入っている', () => {
    for (const lang of ['ja', 'en'] as const) {
      expect(RULE_PAGES[lang]).toHaveLength(RULE_PAGE_COUNT)
      for (const page of RULE_PAGES[lang]) {
        expect(page.title).not.toBe('')
        expect(page.lines.length).toBeGreaterThan(0)
      }
    }
  })

  it('t() は言語別の文言を返す', () => {
    expect(t('ja', 'modePractice')).toBe('れんしゅう')
    expect(t('en', 'modePractice')).toBe('PRACTICE')
  })
})
