// シェア文言・フォールバックURLのテスト

import { afterEach, describe, expect, it, vi } from 'vitest'
import { sharePlay, shareText, xIntentUrl } from './share'

describe('shareText', () => {
  it('スコアとハッシュタグを含む', () => {
    expect(shareText({ score: 81 })).toBe('「Cubeでハノイ」で 81てん とったよ! #pyconjp')
  })
})

describe('sharePlay', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('Web Share API 非対応なら X フォールバックを開く', async () => {
    const open = vi.fn()
    vi.stubGlobal('navigator', {})
    vi.stubGlobal('window', { open })
    await sharePlay({ score: 81 }, 'https://example.com/records/x')
    expect(open).toHaveBeenCalledWith(
      xIntentUrl(shareText({ score: 81 }), 'https://example.com/records/x'),
      '_blank',
      'noopener',
    )
  })

  it('navigator.share がキャンセル(AbortError)ならフォールバックしない', async () => {
    const open = vi.fn()
    const abort = new Error('cancelled')
    abort.name = 'AbortError'
    vi.stubGlobal('navigator', { share: vi.fn().mockRejectedValue(abort) })
    vi.stubGlobal('window', { open })
    await sharePlay({ score: 81 }, 'https://example.com/records/x')
    expect(open).not.toHaveBeenCalled()
  })

  it('navigator.share がキャンセル以外で失敗したら X フォールバックを開く', async () => {
    const open = vi.fn()
    vi.stubGlobal('navigator', { share: vi.fn().mockRejectedValue(new Error('denied')) })
    vi.stubGlobal('window', { open })
    await sharePlay({ score: 81 }, 'https://example.com/records/x')
    expect(open).toHaveBeenCalledTimes(1)
  })
})

describe('xIntentUrl', () => {
  it('本文とURLをエンコードしてツイート画面URLを組み立てる', () => {
    const url = xIntentUrl('あ #tag', 'https://hanoi-cube.web.app/records/x')
    expect(url).toMatch(/^https:\/\/twitter\.com\/intent\/tweet\?/)
    const params = new URL(url).searchParams
    expect(params.get('text')).toBe('あ #tag')
    expect(params.get('url')).toBe('https://hanoi-cube.web.app/records/x')
  })
})
