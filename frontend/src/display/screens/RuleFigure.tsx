// ルールダイアログの図版(SVG)。データは ruleFigures.ts。
// 色はレトロ基調(retro.css の --neon 系)に、箱だけ実物色を使う。

import type { Lang } from '../../contracts/ws'
import {
  badgeLayout,
  BASE_Y,
  BOX_COLOR,
  BOX_HEIGHT,
  BOX_WIDTH,
  boxTopY,
  type FigPanel,
  type FigSize,
  type FigStack,
  figureWidth,
  JOINER_WIDTH,
  PANEL_GAP,
  PANEL_HEIGHT,
  panelOffsets,
  panelWidth,
  POLE_TOP_Y,
  type RuleFigure as RuleFigureData,
  towerCenterX,
} from './ruleFigures'

const NEON = '#7ee06a'
const NEON_STRONG = '#b9ff8e'
const NEON_BASE = '#438532'
const NG = '#ff5c5c'
const TOWER_LABELS = ['A', 'B', 'C']
const FONT = "'DotGothic16', 'Hiragino Kaku Gothic StdN', 'Osaka-Mono', 'MS Gothic', monospace"

export function RuleFigure({ fig, lang }: { fig: RuleFigureData; lang: Lang }) {
  const width = figureWidth(fig)
  const offsets = panelOffsets(fig)
  // キャプション分の余白を下に足す
  const height = PANEL_HEIGHT + 30
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={fig.panels.map((p) => p.caption?.[lang] ?? '').join(' / ')}
      style={{ fontFamily: FONT, letterSpacing: '0.08em' }}
    >
      <defs>
        <marker
          id="rule-arrow-ok"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="3.6"
          markerHeight="3.6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill={NEON_STRONG} />
        </marker>
        <marker
          id="rule-arrow-ng"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="3.6"
          markerHeight="3.6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill={NG} />
        </marker>
      </defs>
      {fig.panels.map((panel, i) => (
        <g key={i} transform={`translate(${offsets[i]} 0)`}>
          <Panel panel={panel} lang={lang} />
        </g>
      ))}
      {fig.joiner &&
        fig.panels.slice(1).map((_, i) => {
          const x = offsets[i] + panelWidth(fig.panels[i]) + PANEL_GAP
          return (
            <g key={`j${i}`} transform={`translate(${x} 0)`}>
              <Joiner kind={fig.joiner!} />
            </g>
          )
        })}
    </svg>
  )
}

function Joiner({ kind }: { kind: 'arrow' | 'mirror' }) {
  const cy = BASE_Y - 44
  if (kind === 'arrow') {
    return (
      <line
        x1={4}
        y1={cy}
        x2={JOINER_WIDTH - 6}
        y2={cy}
        stroke={NEON_STRONG}
        strokeWidth={5}
        markerEnd="url(#rule-arrow-ok)"
      />
    )
  }
  // 鏡像: 縦の鏡線 + ⇄
  return (
    <g>
      <line
        x1={JOINER_WIDTH / 2}
        y1={POLE_TOP_Y - 10}
        x2={JOINER_WIDTH / 2}
        y2={BASE_Y + 8}
        stroke={NEON_BASE}
        strokeWidth={3}
        strokeDasharray="6 6"
      />
      <line
        x1={6}
        y1={cy}
        x2={JOINER_WIDTH - 6}
        y2={cy}
        stroke={NEON_STRONG}
        strokeWidth={5}
        markerStart="url(#rule-arrow-ok)"
        markerEnd="url(#rule-arrow-ok)"
      />
    </g>
  )
}

function Panel({ panel, lang }: { panel: FigPanel; lang: Lang }) {
  const w = panelWidth(panel)
  return (
    <g>
      {panel.towers.length > 0 && (
        <line
          x1={6}
          y1={BASE_Y}
          x2={w - 6}
          y2={BASE_Y}
          stroke={NEON_BASE}
          strokeWidth={5}
          strokeLinecap="round"
        />
      )}
      {panel.towers.map((stack, t) => (
        <Tower
          key={t}
          index={t}
          stack={stack}
          label={panel.towerLabels ? TOWER_LABELS[t] : undefined}
        />
      ))}
      {panel.move && <MoveArrow panel={panel} />}
      {panel.verdict && <Verdict kind={panel.verdict} x={w - 26} y={26} />}
      {panel.badge && <Badge text={panel.badge[lang]} w={w} hasTowers={panel.towers.length > 0} />}
      {panel.caption && (
        <text
          x={w / 2}
          y={PANEL_HEIGHT + 16}
          textAnchor="middle"
          fontSize={17}
          fill={NEON}
          style={{ textShadow: '0 0 6px rgba(126,224,106,0.55)' }}
        >
          {panel.caption[lang]}
        </text>
      )}
    </g>
  )
}

function Tower({ index, stack, label }: { index: number; stack: FigStack; label?: string }) {
  const cx = towerCenterX(index)
  return (
    <g>
      <line x1={cx} y1={POLE_TOP_Y} x2={cx} y2={BASE_Y} stroke={NEON_BASE} strokeWidth={6} />
      {stack.map((size, level) => (
        <Box key={level} size={size} cx={cx} level={level} />
      ))}
      {label && (
        <text
          x={cx}
          y={BASE_Y + 24}
          textAnchor="middle"
          fontSize={18}
          fill={NEON_BASE}
          fontWeight="bold"
        >
          {label}
        </text>
      )}
    </g>
  )
}

function Box({ size, cx, level }: { size: FigSize; cx: number; level: number }) {
  const w = BOX_WIDTH[size]
  const y = boxTopY(level)
  const c = BOX_COLOR[size]
  return (
    <g>
      <rect
        x={cx - w / 2}
        y={y + 1}
        width={w}
        height={BOX_HEIGHT - 2}
        rx={4}
        fill={c.fill}
        stroke={c.edge}
        strokeWidth={3}
      />
      {/* ハイライト(立体感) */}
      <rect
        x={cx - w / 2 + 5}
        y={y + 5}
        width={w - 10}
        height={5}
        rx={2}
        fill="rgba(255,255,255,0.35)"
      />
    </g>
  )
}

/** 箱を動かす矢印(移動元の箱の上から移動先の塔の上へ) */
function MoveArrow({ panel }: { panel: FigPanel }) {
  const { from, to, boxIndex } = panel.move!
  const fromStack = panel.towers[from]
  const toStack = panel.towers[to]
  const level = boxIndex ?? fromStack.length - 1
  const ng = panel.verdict === 'ng'
  const color = ng ? NG : NEON_STRONG
  const x1 = towerCenterX(from)
  const y1 = boxTopY(level) + BOX_HEIGHT / 2
  const x2 = towerCenterX(to)
  const y2 = boxTopY(toStack.length) - 6
  const midY = Math.min(y1, y2) - 40
  // 移動元の箱に色枠を付けて「この箱」を示す
  const size = fromStack[level]
  const w = BOX_WIDTH[size]
  return (
    <g>
      <rect
        x={x1 - w / 2 - 4}
        y={boxTopY(level) - 3}
        width={w + 8}
        height={BOX_HEIGHT + 6}
        rx={6}
        fill="none"
        stroke={color}
        strokeWidth={3}
        strokeDasharray={ng ? '5 4' : undefined}
      />
      <path
        d={`M${x1 + (x2 > x1 ? w / 2 + 4 : -w / 2 - 4)},${y1} Q${(x1 + x2) / 2},${midY} ${x2},${y2}`}
        fill="none"
        stroke={color}
        strokeWidth={5}
        strokeLinecap="round"
        markerEnd={ng ? 'url(#rule-arrow-ng)' : 'url(#rule-arrow-ok)'}
      />
    </g>
  )
}

function Verdict({ kind, x, y }: { kind: 'ok' | 'ng'; x: number; y: number }) {
  if (kind === 'ok') {
    return (
      <g>
        <circle
          cx={x}
          cy={y}
          r={16}
          fill="rgba(126,224,106,0.15)"
          stroke={NEON_STRONG}
          strokeWidth={5}
        />
      </g>
    )
  }
  return (
    <g stroke={NG} strokeWidth={6} strokeLinecap="round">
      <line x1={x - 13} y1={y - 13} x2={x + 13} y2={y + 13} />
      <line x1={x + 13} y1={y - 13} x2={x - 13} y2={y + 13} />
    </g>
  )
}

function Badge({ text, w, hasTowers }: { text: string; w: number; hasTowers: boolean }) {
  // 塔があるコマでは棒の上、ないコマでは中央に大きく
  const cy = hasTowers ? POLE_TOP_Y - 16 : BASE_Y - 56
  const { fontSize, width: bw } = badgeLayout(text, w, hasTowers)
  return (
    <g>
      <rect
        x={w / 2 - bw / 2}
        y={cy - fontSize * 0.9}
        width={bw}
        height={fontSize * 1.8}
        rx={8}
        fill="rgba(5,14,5,0.9)"
        stroke={NEON_STRONG}
        strokeWidth={3}
      />
      <text
        x={w / 2}
        y={cy + fontSize * 0.35}
        textAnchor="middle"
        fontSize={fontSize}
        fill={NEON_STRONG}
        fontWeight="bold"
      >
        {text}
      </text>
    </g>
  )
}
