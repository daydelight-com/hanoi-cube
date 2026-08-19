// ルールダイアログの図版データ(仕様§5.4 / §5.13「ページ図版は日英2式」)。
// 描画(SVG)は RuleFigure.tsx。ここは純データ+レイアウト計算のみでテスト対象。
// 図版は「小さい子でも文字なしで分かる」ことを狙い、実物の箱色(大=緑/中=橙/小=水色)で
// 塔に積んだ箱を描き、○×印と矢印で可否を示す。文言の正は docs/game/hanoi_arrange_rules.md。

import type { Lang } from '../../contracts/ws'

/** 箱サイズ(大・中・小)。盤面契約の BoxSize と同義だが図版専用に短縮表記 */
export type FigSize = 'L' | 'M' | 'S'

/** 1本の塔の中身(下→上) */
export type FigStack = FigSize[]

/** 図版1コマ */
export interface FigPanel {
  /** 塔(左→右)。各塔は下→上の箱列 */
  towers: FigStack[]
  /** ○×印(コマ右上) */
  verdict?: 'ok' | 'ng'
  /** 箱を動かす矢印。boxIndex 省略時はいちばん上の箱 */
  move?: { from: number; to: number; boxIndex?: number }
  /** コマ下の短い説明(日英) */
  caption?: Record<Lang, string>
  /** コマ内に表示するバッジ(得点式など。日英) */
  badge?: Record<Lang, string>
  /** 塔の足元に A/B/C ラベルを出す */
  towerLabels?: boolean
}

/** コマとコマの間に描く記号 */
export type FigJoiner = 'arrow' | 'mirror'

export interface RuleFigure {
  panels: FigPanel[]
  joiner?: FigJoiner
}

// ---- 寸法(SVGユーザー座標。viewBox で拡縮するので絶対値に意味はない) ----

export const BOX_WIDTH: Record<FigSize, number> = { L: 76, M: 56, S: 38 }
export const BOX_HEIGHT = 26
/** 実物の箱の色(frontend/public/textures の cube_l/m/s に合わせる) */
export const BOX_COLOR: Record<FigSize, { fill: string; edge: string }> = {
  L: { fill: '#4caf50', edge: '#1b5e20' },
  M: { fill: '#ef8f1f', edge: '#7a3e00' },
  S: { fill: '#6dd3f0', edge: '#0d5c75' },
}
export const TOWER_PITCH = 96
export const PANEL_PAD_X = 18
export const PANEL_HEIGHT = 176
/** 塔の底面(箱を置く基準線)の y */
export const BASE_Y = 140
/** 棒の上端 y */
export const POLE_TOP_Y = 38
export const JOINER_WIDTH = 56
export const PANEL_GAP = 24
/** 塔のないコマ(バッジだけ)の幅 */
export const BADGE_PANEL_WIDTH = 150

export function panelWidth(panel: FigPanel): number {
  if (panel.towers.length === 0) return BADGE_PANEL_WIDTH
  return PANEL_PAD_X * 2 + panel.towers.length * TOWER_PITCH
}

/** コマ内での塔の中心 x */
export function towerCenterX(index: number): number {
  return PANEL_PAD_X + TOWER_PITCH * index + TOWER_PITCH / 2
}

/** 下から i 段目の箱の上端 y */
export function boxTopY(level: number): number {
  return BASE_Y - BOX_HEIGHT * (level + 1)
}

/** 図版全体の幅(コマ+つなぎ記号) */
export function figureWidth(fig: RuleFigure): number {
  const panels = fig.panels.reduce((sum, p) => sum + panelWidth(p), 0)
  const gaps = Math.max(0, fig.panels.length - 1)
  const joiner = fig.joiner ? JOINER_WIDTH : 0
  return panels + gaps * (PANEL_GAP * 2 + joiner)
}

/** 各コマの左端 x(図版座標) */
export function panelOffsets(fig: RuleFigure): number[] {
  const offsets: number[] = []
  let x = 0
  const joiner = fig.joiner ? JOINER_WIDTH : 0
  fig.panels.forEach((p, i) => {
    if (i > 0) x += PANEL_GAP * 2 + joiner
    offsets.push(x)
    x += panelWidth(p)
  })
  return offsets
}

/** 文字幅の概算係数(fontSize あたり) */
export const BADGE_CHAR_RATIO = 0.78
export const BADGE_PAD_X = 36

/**
 * バッジの文字サイズと枠幅。文字数が多いときは縮めてコマ幅(=viewBox)に収める
 * (英語の得点式など。コマ外は描画範囲外で欠けるため)。
 */
export function badgeLayout(
  text: string,
  panelW: number,
  hasTowers: boolean,
): { fontSize: number; width: number } {
  const baseSize = hasTowers ? 20 : 26
  const fontSize = Math.min(baseSize, (panelW - BADGE_PAD_X) / (text.length * BADGE_CHAR_RATIO))
  const width = Math.max(panelW - 12, text.length * fontSize * BADGE_CHAR_RATIO + BADGE_PAD_X)
  return { fontSize, width }
}

/** 左右反転(A⇄C)。クリア条件の図に使う */
export function mirrorTowers(towers: FigStack[]): FigStack[] {
  return [...towers].reverse()
}

// ---- ページごとの図版(RULE_PAGES と同じ順。page_count=5) ----

const START: FigStack[] = [['L', 'M', 'S'], ['L', 'M'], ['L']]

export const RULE_FIGURES: RuleFigure[] = [
  // 0 ゲームのあらまし: 積む → はんてい → ポイント
  {
    joiner: 'arrow',
    panels: [
      { towers: START, towerLabels: true, caption: { ja: 'はこを つむ', en: 'STACK' } },
      {
        towers: [],
        badge: { ja: 'はんてい!', en: 'JUDGE!' },
        caption: { ja: 'ボタンを おす', en: 'PRESS' },
      },
      { towers: [], badge: { ja: '+18', en: '+18' }, caption: { ja: 'ポイント!', en: 'POINTS!' } },
    ],
  },
  // 1 つみかた ○×
  {
    panels: [
      {
        towers: [['L', 'M', 'S']],
        verdict: 'ok',
        caption: { ja: 'おおきい→ちいさい', en: 'BIG → SMALL' },
      },
      {
        towers: [['S', 'L']],
        verdict: 'ng',
        caption: { ja: 'ちいさいのが した', en: 'SMALL BELOW' },
      },
      { towers: [['M', 'M']], verdict: 'ng', caption: { ja: 'おなじ おおきさ', en: 'SAME SIZE' } },
    ],
  },
  // 2 うごかしかた ○×
  {
    panels: [
      {
        towers: [['M', 'S'], ['L']],
        move: { from: 0, to: 1 },
        verdict: 'ok',
        caption: { ja: 'おおきい はこの うえ', en: 'ONTO BIGGER' },
      },
      {
        towers: [['L', 'M'], ['S']],
        move: { from: 0, to: 1 },
        verdict: 'ng',
        caption: { ja: 'ちいさい はこの うえ', en: 'ONTO SMALLER' },
      },
      {
        towers: [['L', 'M', 'S'], []],
        move: { from: 0, to: 1, boxIndex: 1 },
        verdict: 'ng',
        caption: { ja: 'したの はこは だめ', en: 'NOT THE TOP' },
      },
    ],
  },
  // 3 クリアとは: さいしょ ⇄ ひっくりかえし
  {
    joiner: 'mirror',
    panels: [
      { towers: START, towerLabels: true, caption: { ja: 'さいしょ', en: 'START' } },
      {
        towers: mirrorTowers(START),
        towerLabels: true,
        verdict: 'ok',
        caption: { ja: 'ひだりみぎ はんたい', en: 'MIRRORED' },
      },
    ],
  },
  // 4 とくてん: はこのかず × てすう
  {
    panels: [
      {
        towers: START,
        towerLabels: true,
        badge: { ja: '6こ × 3て = 18', en: '6 BOXES × 3 MOVES = 18' },
      },
    ],
  },
]
