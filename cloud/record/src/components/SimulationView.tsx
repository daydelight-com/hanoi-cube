// 最短手順のシミュレーション再生(仕様§5.10)。
// 「進む/戻る」で1手ずつ前後できる。事前計算済みの min_path を使用する。

import { useState } from 'react'
import type { Move } from '../contracts/precompute'
import type { TowerBoxIds } from '../contracts/play'
import { stacksAfter } from '../simulation'
import { BoardView } from './BoardView'

const TOWER_LABEL = { A: 'ひだり', B: 'まんなか', C: 'みぎ' } as const
const SIZE_LABEL = { L: 'おおきい', M: 'ちゅうくらい', S: 'ちいさい' } as const

export function SimulationView({ initial, path }: { initial: TowerBoxIds; path: Move[] }) {
  const [step, setStep] = useState(0)
  const { stacks, movedBoxId } = stacksAfter(initial, path, step)
  const move = step > 0 ? path[step - 1] : null
  const done = step === path.length

  return (
    <div className="simulation">
      <BoardView stacks={stacks} highlightBoxId={movedBoxId} />
      <p className="simulation-caption">
        {move === null
          ? 'はんてい したときの ならべかた'
          : `${SIZE_LABEL[move.size]}はこを ${TOWER_LABEL[move.from]}から ${TOWER_LABEL[move.to]}へ`}
        {done && <strong> → クリア!</strong>}
      </p>
      <div className="simulation-controls">
        <button type="button" onClick={() => setStep(step - 1)} disabled={step === 0}>
          ← もどる
        </button>
        <span className="simulation-step">
          {step} / {path.length} て
        </span>
        <button type="button" onClick={() => setStep(step + 1)} disabled={done}>
          すすむ →
        </button>
      </div>
    </div>
  )
}
