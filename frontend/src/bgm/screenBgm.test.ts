import { describe, expect, it } from 'vitest'
import type { ScreenId } from '../contracts/ws'
import { bgmTrackForScreen } from './screenBgm'

describe('bgmTrackForScreen', () => {
  it('待機〜練習は NEON STACKS を継続する', () => {
    const screens: ScreenId[] = [
      'idle_title',
      'idle_ranking',
      'mode_select',
      'rule_dialog',
      'practice',
    ]
    expect(screens.map(bgmTrackForScreen)).toEqual(screens.map(() => 'waiting'))
  })

  it('カウントダウンは無音、本番入場で CUBE RUSH を開始する', () => {
    expect(bgmTrackForScreen('game_countdown')).toBeNull()
    expect(bgmTrackForScreen('game_play')).toBe('gameplay')
  })

  it('リザルト〜QRは SCORE GLOW を継続する', () => {
    const screens: ScreenId[] = ['result', 'ranking', 'qr']
    expect(screens.map(bgmTrackForScreen)).toEqual(screens.map(() => 'result'))
  })

  it('snapshot前は無音', () => {
    expect(bgmTrackForScreen(null)).toBeNull()
  })
})
