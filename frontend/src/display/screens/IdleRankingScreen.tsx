// 待機画面(ランキング)。仕様§5.2: 全件をせり上がり演出で表示する。
// 表は常に「上位が上」の並び(1位が先頭)で描画し、表全体を画面下から
// せり上げる。1画面に収まるならそのまま見出しの下で停止し、収まらないなら
// 最後の行まで流し切ってから先頭(1位)へ戻して静止する。サーバーはこの静止の
// あと TAIL_MS でタイトルへ戻るため、最後に見えるのは必ず1位になる。
// せり上がり時間はサーバーのタイマー(state/machine.py の行数比例+クランプ)と
// 同じ式で算出し、演出とタイムアウトのタイミングを合わせる。

import { useEffect, useRef } from 'react'
import type { Lang, RankingEntry } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'
import { idleRankingRows } from './idleRankingRows'
import { idleRankingEndY, idleRankingScrollMs } from './idleRankingTiming'

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
  const areaRef = useRef<HTMLDivElement | null>(null)
  const riseRef = useRef<HTMLDivElement | null>(null)

  // 表示順は常に「1位 → … → 最下位」(上位が上)
  const ordered = idleRankingRows(entries)

  useEffect(() => {
    const area = areaRef.current
    const el = riseRef.current
    if (!area || !el) return
    const duration = idleRankingScrollMs(entries.length)
    // 始点は表示領域の下端(画面下から現れる)
    const from = area.clientHeight
    const end = idleRankingEndY(el.offsetHeight, area.clientHeight)
    el.style.transition = 'none'
    el.style.transform = `translateY(${from}px)`
    // 初期位置を反映してから transition を有効化する(reflow を挟む)
    void el.getBoundingClientRect()
    el.style.transition = `transform ${duration}ms linear`
    el.style.transform = `translateY(${end}px)`
    // 1画面に収まるなら終点が見出し直下(=1位が最上段)なので、そのまま静止する
    if (end === 0) return
    // 収まらない場合は流し切ったあと先頭へ戻し、最後に1位を見せて静止する
    const timer = setTimeout(() => {
      el.style.transition = 'none'
      el.style.transform = 'translateY(0)'
    }, duration)
    return () => clearTimeout(timer)
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
      <div ref={areaRef} className="retro-ranking-rise-area">
        {/* 初期値は effect(計測)が走る前の1フレーム用。表示領域より必ず下になるよう
            表の高さに依存しない 100vh を使う(100% だと短い表が最初の1frameで見える) */}
        <div ref={riseRef} style={{ transform: 'translateY(100vh)' }}>
          <RankingTable lang={lang} entries={ordered} />
        </div>
      </div>
    </div>
  )
}
