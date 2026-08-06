// 盤面を正面から見た2Dレンダリング(仕様§5.10)。
// 同サイズの箱は色では同じだが、個体番号のバッジで見分けられる(firestore.md §1 の
// tower_box_ids が表示専用に個体を持つ理由)。

import type { SizeChar } from '../contracts/board'
import type { TowerBoxIds } from '../contracts/play'
import { boxSerial, boxSize } from '../simulation'

const VIEW_W = 312
const VIEW_H = 108
const TOWER_X = [52, 156, 260] // 各塔の中心
const BASE_Y = 92
const BOX_H = 24
const BOX_W: Record<SizeChar, number> = { L: 88, M: 60, S: 40 }
const BOX_FILL: Record<SizeChar, string> = { L: '#e2574c', M: '#58b368', S: '#4a90d9' }

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
      {TOWER_X.map((x, i) => (
        <rect
          key={i}
          x={x - 50}
          y={BASE_Y}
          width={100}
          height={6}
          rx={3}
          className="board-view-base"
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
                rx={4}
                fill={BOX_FILL[size]}
                stroke={highlighted ? '#111' : 'rgba(0,0,0,0.25)'}
                strokeWidth={highlighted ? 3 : 1}
              />
              <circle cx={x + w / 2} cy={y + (BOX_H - 2) / 2} r={8} fill="rgba(255,255,255,0.85)" />
              <text
                x={x + w / 2}
                y={y + (BOX_H - 2) / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={11}
                fontWeight={700}
                fill="#333"
              >
                {boxSerial(boxId)}
              </text>
            </g>
          )
        }),
      )}
    </svg>
  )
}
