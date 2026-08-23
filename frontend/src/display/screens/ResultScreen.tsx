// リザルト画面(仕様§5.7)。スコア・失敗数・暫定順位と名前入力欄のミラー表示。
// 「入力」「決定」のフォーカス・入力モードはサーバーの ctx に追従する。
// 決定は 0 文字のとき無効表示(実際のガードはサーバー側。screens.md 行24)。

import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink, MenuItem, RetroFrame } from '../ui/Retro'

export function ResultScreen({
  lang,
  ctx,
  onSelect,
  onNameType,
  onNameDone,
}: {
  lang: Lang
  ctx: ScreenCtxMap['result']
  onSelect: (target: 'input' | 'decide') => void
  onNameType: (text: string) => void
  onNameDone: () => void
}) {
  const typing = ctx.input_mode === 'name'
  return (
    <div className="retro-screen">
      <h2 className="retro-heading">{t(lang, 'resultHeading')}</h2>
      <RetroFrame>
        <div className="retro-result-stats">
          <div>
            <div className="retro-hud-label">{t(lang, 'scoreLabel')}</div>
            <div className="retro-result-score">{ctx.score}</div>
          </div>
          <div>
            <div className="retro-hud-label">{t(lang, 'resultRank')}</div>
            <div className="retro-result-sub">{ctx.rank}</div>
          </div>
          <div>
            <div className="retro-hud-label">{t(lang, 'failLabel')}</div>
            <div className="retro-result-sub">{ctx.fail_count}</div>
          </div>
        </div>
        <div className="retro-result-name">
          <span className="retro-hud-label">{t(lang, 'resultNameLabel')}</span>
          {typing ? (
            <input
              className="retro-name-field typing"
              autoFocus
              value={ctx.name_text}
              maxLength={10}
              autoComplete="off"
              onChange={(event) => onNameType(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return
                event.preventDefault()
                onNameDone()
              }}
            />
          ) : (
            <span className="retro-name-field">{ctx.name_text}</span>
          )}
        </div>
      </RetroFrame>
      {typing ? (
        <div className="retro-text">
          <Blink>{t(lang, 'resultTyping')}</Blink>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '3vw' }}>
            <MenuItem focused={ctx.focus === 'input'} onClick={() => onSelect('input')}>
              {t(lang, 'resultInputButton')}
            </MenuItem>
            <div className={ctx.name_text.length === 0 ? 'retro-disabled' : undefined}>
              <MenuItem focused={ctx.focus === 'decide'} onClick={() => onSelect('decide')}>
                {t(lang, 'resultDecideButton')}
              </MenuItem>
            </div>
          </div>
          <div className="retro-text">{t(lang, 'resultHint')}</div>
        </>
      )}
    </div>
  )
}
