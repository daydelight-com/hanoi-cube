// ランキング画面(仕様§5.8)。全件表示し、直前プレイの行が見える位置まで
// スクロールした状態で表示する。決定ガード(3秒)はサーバー側(screens.md 行25)。

import { useEffect, useRef } from 'react'
import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'
import { RankingTable } from './IdleRankingScreen'

export function RankingScreen({
  lang,
  ctx,
  onNext,
}: {
  lang: Lang
  ctx: ScreenCtxMap['ranking']
  onNext: () => void
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = scrollRef.current
    if (!container || ctx.highlight_play_id === null) return
    const row = container.querySelector<HTMLElement>('[data-highlight="true"]')
    // ハイライト行がビューポート中央に来るようスクロールした状態で表示(§5.8)
    if (row) {
      container.scrollTop = row.offsetTop - container.clientHeight / 2 + row.offsetHeight / 2
    }
  }, [ctx.entries, ctx.highlight_play_id])

  return (
    <div className="retro-screen" style={{ justifyContent: 'flex-start' }}>
      <h2 className="retro-heading" style={{ marginTop: '4vh' }}>
        ★ {t(lang, 'rankingHeading')} ★
      </h2>
      <div ref={scrollRef} className="retro-ranking-scroll">
        {ctx.entries.length === 0 ? (
          <div className="retro-text">{t(lang, 'rankingEmpty')}</div>
        ) : (
          <RankingTable lang={lang} entries={ctx.entries} highlightPlayId={ctx.highlight_play_id} />
        )}
      </div>
      <button
        type="button"
        className="retro-text retro-text-button"
        style={{ marginBottom: '3vh' }}
        onClick={onNext}
      >
        <Blink>{t(lang, 'rankingNext')}</Blink>
      </button>
    </div>
  )
}
