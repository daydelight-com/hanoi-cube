// 盤面を正面から見た2Dレンダリング(仕様§5.10)。
// 見た目はゲーム画面の3D盤面(frontend/src/three/textures.ts)に合わせる:
// 箱はサイズ別カラー(L=赤/M=緑/S=青)+黒縁+「大1」形式の白ラベル、
// 台はマットの暗緑地+ネオン枠。同サイズの箱はラベルの個体番号で見分けられる
// (firestore.md §1 の tower_box_ids が表示専用に個体を持つ理由)。

import type { SizeChar } from '../contracts/board'
import type { TowerBoxIds } from '../contracts/play'
import { boxSerial, boxSize } from '../simulation'

const VIEW_W = 312
const VIEW_H = 116
const TOWER_X = [52, 156, 260] // 各塔の中心
const BASE_Y = 98
const BOX_H = 26
const BOX_W: Record<SizeChar, number> = { L: 88, M: 60, S: 40 }
// ゲーム画面の SIZE_COLOR(textures.ts)と同一
const BOX_FILL: Record<SizeChar, string> = { L: '#c0392b', M: '#438532', S: '#2e6da4' }
const SIZE_KANJI: Record<SizeChar, string> = { L: '大', M: '中', S: '小' }

export function BoardView({
  stacks,
  highlightBoxId = null,
}: {
  stacks: TowerBoxIds
  highlightBoxId?: string | null
}) {
  return (
    <svg
      className="board-view"
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      role="img"
      aria-label={stacks.map((t) => t.map(boxSize).join('') || 'なし').join(' / ')}
    >
      {/* マット(暗緑地+ネオン塔枠。buildMatTexture と同系色) */}
      <rect x={0} y={BASE_Y} width={VIEW_W} height={VIEW_H - BASE_Y} fill="#10240f" />
      {TOWER_X.map((x, i) => (
        <rect
          key={i}
          x={x - 50}
          y={BASE_Y}
          width={100}
          height={6}
          fill="none"
          stroke="#7ee06a"
          strokeWidth={2}
        />
      ))}
      {stacks.flatMap((tower, towerIndex) =>
        tower.map((boxId, level) => {
          const size = boxSize(boxId)
          const w = BOX_W[size]
          const x = TOWER_X[towerIndex] - w / 2
          const y = BASE_Y - BOX_H * (level + 1)
          const highlighted = boxId === highlightBoxId
          return (
            <g key={boxId}>
              <rect
                x={x}
                y={y}
                width={w}
                height={BOX_H - 2}
                fill={BOX_FILL[size]}
                stroke={highlighted ? '#b9ff8e' : 'rgba(0,0,0,0.45)'}
                strokeWidth={highlighted ? 3 : 2}
              />
              <text
                x={x + w / 2}
                y={y + (BOX_H - 2) / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={13}
                fontWeight={700}
                fill="rgba(255,255,255,0.92)"
              >
                {SIZE_KANJI[size]}
                {boxSerial(boxId)}
              </text>
            </g>
          )
        }),
      )}
    </svg>
  )
}
