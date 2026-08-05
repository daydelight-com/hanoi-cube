// 本番のカウントダウン(§5.6: 3,2,1,GO! 中は判定不可・3Dは動く)と計測中画面。
// 背景は透過で3D盤面を見せる。文言のうち 3/2/1/GO・数値は言語非依存(§5.13)。

import { useEffect, useState } from 'react'
import type { Judge, Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { formatRemaining, isTimeCritical } from './format'
import { JudgeFlash } from './JudgeFlash'

// サーバーは countdown:go と同時に game_play へ遷移する(machine.py: GOと同時に
// 計測開始)ため、GO! は game_play 入場直後にディスプレイ側で短時間表示する
const GO_FLASH_MS = 800

export function GameCountdownScreen({ ctx }: { ctx: ScreenCtxMap['game_countdown'] }) {
  const text = ctx.value === 'go' ? 'GO!' : ctx.value
  return (
    <div className="retro-screen retro-screen--clear">
      {/* key で値が変わるたびにズームアニメーションを再生する */}
      <div key={ctx.value} className={`retro-countdown${ctx.value === 'go' ? ' go' : ''}`}>
        {text}
      </div>
    </div>
  )
}

export function GamePlayScreen({
  lang,
  ctx,
  lastJudge,
}: {
  lang: Lang
  ctx: ScreenCtxMap['game_play']
  lastJudge: Judge | null
}) {
  // 満タンの残り時間で入場したときだけ GO! を出す(途中再接続では出さない)
  const [startedFull] = useState(ctx.remaining_ms >= 60_000)
  const [goExpired, setGoExpired] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setGoExpired(true), GO_FLASH_MS)
    return () => clearTimeout(timer)
  }, [])

  const critical = isTimeCritical(ctx.remaining_ms)
  return (
    <div className="retro-screen retro-screen--clear">
      <div className="retro-hud retro-hud--left">
        <div className="retro-hud-label">{t(lang, 'scoreLabel')}</div>
        <div className="retro-hud-value">{ctx.score}</div>
      </div>
      <div className="retro-hud retro-hud--center">
        <div className="retro-hud-label">{t(lang, 'timeLabel')}</div>
        <div className={`retro-hud-timer${critical ? ' critical' : ''}`}>
          {formatRemaining(ctx.remaining_ms)}
        </div>
      </div>
      <div className="retro-hud retro-hud--right">
        <div className="retro-hud-label">{t(lang, 'failLabel')}</div>
        <div className="retro-hud-value">{ctx.fail_count}</div>
      </div>
      {startedFull && !goExpired && <div className="retro-countdown go">GO!</div>}
      <JudgeFlash lang={lang} judge={lastJudge} />
    </div>
  )
}
