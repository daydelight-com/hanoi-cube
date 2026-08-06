// 判定履歴カード(仕様§5.10)。
// 得点した配置: 点数表示、タップで最短手順シミュレーションを開閉。
// クリア不可: ×。重複(完全同一・鏡像とも): △、タップで得点した元カードへスクロール。

import { useState } from 'react'
import { towerTuple, type JudgementDoc } from '../contracts/play'
import { precomputeFor } from '../contracts/precompute'
import { BoardView } from './BoardView'
import { SimulationView } from './SimulationView'

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function JudgementCard({ judgement }: { judgement: JudgementDoc }) {
  const [open, setOpen] = useState(false)
  const { result } = judgement

  const scrollToOriginal = () => {
    if (judgement.dup_of_seq === null) return
    // behavior: 'smooth' は環境によって無動作になる(検証時の内蔵ブラウザで再現)ため即時スクロール
    document
      .getElementById(`judgement-${judgement.dup_of_seq}`)
      ?.scrollIntoView({ block: 'center' })
  }

  return (
    <article id={`judgement-${judgement.seq}`} className={`card card--${result}`}>
      <header className="card-header">
        <span className="card-seq">はんてい {judgement.seq}</span>
        <span className="card-elapsed">⏱ {formatElapsed(judgement.elapsed_ms)}</span>
        {result === 'scored' && (
          <span className="card-badge card-badge--scored">+{judgement.points} てん</span>
        )}
        {result === 'unclearable' && <span className="card-badge card-badge--failed">×</span>}
        {(result === 'duplicate_same' || result === 'duplicate_mirror') && (
          <span className="card-badge card-badge--dup">△</span>
        )}
      </header>

      <BoardView stacks={towerTuple(judgement.tower_box_ids)} />

      {result === 'scored' && (
        <>
          <button type="button" className="card-action" onClick={() => setOpen(!open)}>
            {open ? 'とじる' : `さいたん ${judgement.min_moves} て の クリアてじゅんを みる ▶`}
          </button>
          {open && <Simulation judgement={judgement} />}
        </>
      )}
      {result === 'unclearable' && <p className="card-note">クリアできない ならべかた でした</p>}
      {result === 'duplicate_same' && (
        <button type="button" className="card-action" onClick={scrollToOriginal}>
          おなじ ならべかたで とくてん ずみ(はんてい {judgement.dup_of_seq} へ)
        </button>
      )}
      {result === 'duplicate_mirror' && (
        <button type="button" className="card-action" onClick={scrollToOriginal}>
          ひだりみぎ ぎゃくの ならべかたで とくてん ずみ(はんてい {judgement.dup_of_seq} へ)
        </button>
      )}
    </article>
  )
}

function Simulation({ judgement }: { judgement: JudgementDoc }) {
  // 事前計算テーブル(同梱)から board で最短手順を引く(firestore.md §1)
  const path = precomputeFor(judgement.board).min_path
  if (path === null) return <p className="card-note">てじゅんデータが みつかりません</p>
  return <SimulationView initial={towerTuple(judgement.tower_box_ids)} path={path} />
}
