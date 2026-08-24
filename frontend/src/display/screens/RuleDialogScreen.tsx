// ルールダイアログ。仕様§5.4: 複数ページのモーダル。←→でページ切替、決定で閉じる。
// ページ内容は i18n/strings.ts の RULE_PAGES(正: docs/game/hanoi_arrange_rules.md)、
// 図版は ruleFigures.ts(SVG描画は RuleFigure.tsx)。文字が読めない子でも図で分かるよう、
// 図版を主役(上・大きく)、文言を補助(下・短く)に置く。

import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { RULE_PAGES, t } from '../../i18n/strings'
import { PageDots, RetroFrame } from '../ui/Retro'
import { RuleFigure } from './RuleFigure'
import { RULE_FIGURES } from './ruleFigures'

export function RuleDialogScreen({
  lang,
  ctx,
  onClose,
  onPageChange,
}: {
  lang: Lang
  ctx: ScreenCtxMap['rule_dialog']
  onClose: () => void
  onPageChange: (direction: 'left' | 'right') => void
}) {
  const pages = RULE_PAGES[lang]
  // ページ数はサーバー(ctx.page_count)と辞書で二重管理のため、範囲外はクランプして守る
  const page = Math.min(Math.max(ctx.page, 0), pages.length - 1)
  const { title, lines } = pages[page]
  const fig = RULE_FIGURES[page]

  return (
    <div className="retro-screen">
      <RetroFrame
        style={{
          width: '72vw',
          minHeight: '72vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1.5vh',
        }}
      >
        <h2 className="retro-heading" style={{ fontSize: '3vw' }}>
          {page + 1}. {title}
        </h2>
        {fig && (
          <div style={{ width: '100%', height: '34vh' }}>
            <RuleFigure fig={fig} lang={lang} />
          </div>
        )}
        <div
          className="retro-text"
          style={{ textAlign: 'center', fontSize: '1.9vw', lineHeight: 1.7 }}
        >
          {lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1vh' }}>
          <div className="retro-rule-nav">
            <button
              type="button"
              className="retro-rule-nav-button"
              aria-label="Previous page"
              onClick={() => onPageChange('left')}
            >
              ◀
            </button>
            <PageDots page={page} pageCount={ctx.page_count} />
            <button
              type="button"
              className="retro-rule-nav-button"
              aria-label="Next page"
              onClick={() => onPageChange('right')}
            >
              ▶
            </button>
          </div>
          <button
            type="button"
            className="retro-text retro-text-button"
            style={{ fontSize: '1.3vw', color: 'var(--neon-base)' }}
            onClick={onClose}
          >
            {t(lang, 'rulePageNav')} / {t(lang, 'ruleClose')}
          </button>
        </div>
      </RetroFrame>
    </div>
  )
}
