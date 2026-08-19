import { describe, expect, it } from 'vitest'
import { RULE_PAGES } from '../../i18n/strings'
import {
  BADGE_PANEL_WIDTH,
  badgeLayout,
  BOX_WIDTH,
  type FigSize,
  figureWidth,
  JOINER_WIDTH,
  mirrorTowers,
  PANEL_GAP,
  panelOffsets,
  panelWidth,
  RULE_FIGURES,
} from './ruleFigures'

const ORDER: Record<FigSize, number> = { L: 3, M: 2, S: 1 }

describe('ruleFigures', () => {
  it('図版はルールページと同じ数・同じ順で用意されている', () => {
    expect(RULE_FIGURES).toHaveLength(RULE_PAGES.ja.length)
    expect(RULE_FIGURES).toHaveLength(RULE_PAGES.en.length)
  })

  it('全キャプション・バッジは日英とも空でない', () => {
    for (const fig of RULE_FIGURES) {
      for (const panel of fig.panels) {
        for (const text of [panel.caption, panel.badge]) {
          if (!text) continue
          expect(text.ja).not.toBe('')
          expect(text.en).not.toBe('')
        }
      }
    }
  })

  it('○印のコマは積み方・動かし方がルールどおり(×印のコマは違反を含む)', () => {
    const legalStack = (stack: FigSize[]) =>
      stack.every((s, i) => i === 0 || ORDER[s] < ORDER[stack[i - 1]]) && stack.length <= 3
    for (const fig of RULE_FIGURES) {
      for (const panel of fig.panels) {
        if (panel.verdict === 'ok') {
          expect(panel.towers.every(legalStack)).toBe(true)
          if (panel.move) {
            const { from, to, boxIndex } = panel.move
            const src = panel.towers[from]
            const dst = panel.towers[to]
            expect(boxIndex ?? src.length - 1).toBe(src.length - 1)
            const moving = src[src.length - 1]
            expect(dst.length === 0 || ORDER[dst[dst.length - 1]] > ORDER[moving]).toBe(true)
          }
        }
        if (panel.verdict === 'ng') {
          const stackNg = !panel.towers.every(legalStack)
          let moveNg = false
          if (panel.move) {
            const { from, to, boxIndex } = panel.move
            const src = panel.towers[from]
            const dst = panel.towers[to]
            const idx = boxIndex ?? src.length - 1
            moveNg =
              idx !== src.length - 1 ||
              (dst.length > 0 && ORDER[dst[dst.length - 1]] <= ORDER[src[idx]])
          }
          expect(stackNg || moveNg).toBe(true)
        }
      }
    }
  })

  it('移動矢印の参照先は塔と箱の範囲内', () => {
    for (const fig of RULE_FIGURES) {
      for (const panel of fig.panels) {
        if (!panel.move) continue
        const { from, to, boxIndex } = panel.move
        expect(from).toBeLessThan(panel.towers.length)
        expect(to).toBeLessThan(panel.towers.length)
        expect(from).not.toBe(to)
        expect(boxIndex ?? 0).toBeLessThan(panel.towers[from].length)
      }
    }
  })

  it('クリア説明ページは左右反転した盤面を並べている', () => {
    const clearFig = RULE_FIGURES[3]
    expect(clearFig.joiner).toBe('mirror')
    expect(clearFig.panels[1].towers).toEqual(mirrorTowers(clearFig.panels[0].towers))
    expect(mirrorTowers([['L'], ['M'], ['S']])).toEqual([['S'], ['M'], ['L']])
  })

  it('箱の幅は 大 > 中 > 小', () => {
    expect(BOX_WIDTH.L).toBeGreaterThan(BOX_WIDTH.M)
    expect(BOX_WIDTH.M).toBeGreaterThan(BOX_WIDTH.S)
  })

  it('コマ幅とオフセットが整合する(重ならず、図版幅に収まる)', () => {
    for (const fig of RULE_FIGURES) {
      const offsets = panelOffsets(fig)
      expect(offsets).toHaveLength(fig.panels.length)
      expect(offsets[0]).toBe(0)
      for (let i = 1; i < offsets.length; i++) {
        const prevEnd = offsets[i - 1] + panelWidth(fig.panels[i - 1])
        const gap = offsets[i] - prevEnd
        expect(gap).toBe(PANEL_GAP * 2 + (fig.joiner ? JOINER_WIDTH : 0))
      }
      const last = fig.panels.length - 1
      expect(offsets[last] + panelWidth(fig.panels[last])).toBe(figureWidth(fig))
    }
  })

  it('塔のないコマは固定幅', () => {
    expect(panelWidth({ towers: [] })).toBe(BADGE_PANEL_WIDTH)
    expect(panelWidth({ towers: [['L']] })).toBeGreaterThan(0)
  })

  it('バッジは日英ともコマ幅に収まる(長文は縮小)', () => {
    for (const fig of RULE_FIGURES) {
      for (const panel of fig.panels) {
        if (!panel.badge) continue
        const w = panelWidth(panel)
        for (const lang of ['ja', 'en'] as const) {
          const { fontSize, width } = badgeLayout(panel.badge[lang], w, panel.towers.length > 0)
          expect(width).toBeLessThanOrEqual(w)
          expect(fontSize).toBeGreaterThan(10)
        }
      }
    }
    // 短文は縮小されない
    expect(badgeLayout('+18', 150, false).fontSize).toBe(26)
  })
})
