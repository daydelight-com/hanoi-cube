// 待機画面(ランキング)。仕様§5.2: 全件を下位から順にせり上がり、1位まで表示。
// せり上がり時間はサーバーのタイマー(state/machine.py の行数比例+クランプ)と
// 同じ式で算出し、演出とタイムアウトのタイミングを合わせる。

import { useEffect, useRef } from 'react'
import type { Lang, RankingEntry } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { sfx } from '../../sfx/engine'
import { Blink } from '../ui/Retro'
import { idleRankingScrollMs, idleRankingTickTimes } from './idleRankingTiming'

export function RankingTable({
  lang,
  entries,
  highlightPlayId,
}: {
  lang: Lang
  entries: RankingEntry[]
  highlightPlayId?: string | null
}) {
  return (
    <table className="retro-ranking-table">
      <thead>
        <tr>
          <th>{t(lang, 'rankingRank')}</th>
          <th style={{ textAlign: 'left' }}>{t(lang, 'rankingName')}</th>
          <th>{t(lang, 'rankingScore')}</th>
          <th>{t(lang, 'rankingFails')}</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr
            key={e.play_id}
            className={e.rank === 1 ? 'top1' : undefined}
            data-highlight={e.play_id === highlightPlayId ? 'true' : undefined}
            style={
              e.play_id === highlightPlayId ? { background: 'rgba(30, 69, 23, 0.9)' } : undefined
            }
          >
            <td>{e.rank}</td>
            <td className="name">{e.name}</td>
            <td>{e.score}</td>
            <td>{e.fail_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function IdleRankingScreen({ lang, entries }: { lang: Lang; entries: RankingEntry[] }) {
  const riseRef = useRef<HTMLDivElement | null>(null)

  // 下位から順にせり上がるため、コンテナは上から「最下位 → … → 1位」の順に並べる
  // (最初に画面へ入るのはコンテナ先頭=最下位。最後に1位が現れて止まる)
  const ascending = [...entries].sort((a, b) => b.rank - a.rank)

  useEffect(() => {
    const el = riseRef.current
    if (!el) return
    const duration = idleRankingScrollMs(entries.length)
    el.style.transition = 'none'
    el.style.transform = 'translateY(100vh)'
    // 初期位置を反映してから transition を有効化する(reflow を挟む)
    void el.getBoundingClientRect()
    el.style.transition = `transform ${duration}ms linear`
    // 終点はコンテナ末尾(1位)が画面中央やや上に来る位置。CSS keyframes では
    // 終点が要素高に依存して書けないため transition + calc で指定する
    el.style.transform = 'translateY(calc(45vh - 100%))'
  }, [entries])

  // せり上がりに合わせた効果音(§5.12: 1行ごとのティック、1位表示でファンファーレ)。
  // タイマー起点はサーバーと同式の演出時間(idleRankingTiming)に合わせる
  useEffect(() => {
    if (entries.length === 0) return
    const timers = idleRankingTickTimes(entries.length).map((at) =>
      setTimeout(() => sfx.play('rank_tick'), at),
    )
    timers.push(setTimeout(() => sfx.play('fanfare'), idleRankingScrollMs(entries.length)))
    return () => timers.forEach(clearTimeout)
  }, [entries])

  if (entries.length === 0) {
    return (
      <div className="retro-screen">
        <h2 className="retro-heading">{t(lang, 'rankingHeading')}</h2>
        <div className="retro-text">
          <Blink>{t(lang, 'rankingEmpty')}</Blink>
        </div>
      </div>
    )
  }

  return (
    <div className="retro-screen" style={{ justifyContent: 'flex-start', overflow: 'hidden' }}>
      <h2 className="retro-heading" style={{ marginTop: '5vh', zIndex: 1 }}>
        ★ {t(lang, 'rankingHeading')} ★
      </h2>
      <div ref={riseRef} style={{ transform: 'translateY(100vh)' }}>
        <RankingTable lang={lang} entries={ascending} />
      </div>
    </div>
  )
}
