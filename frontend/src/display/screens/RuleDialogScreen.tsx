// ルールダイアログ。仕様§5.4: 複数ページのモーダル。←→でページ切替、決定で閉じる。
// ページ内容は i18n/strings.ts の RULE_PAGES(正: docs/game/hanoi_arrange_rules.md)。

import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { RULE_PAGES, t } from '../../i18n/strings'
import { PageDots, RetroFrame } from '../ui/Retro'

export function RuleDialogScreen({ lang, ctx }: { lang: Lang; ctx: ScreenCtxMap['rule_dialog'] }) {
  const pages = RULE_PAGES[lang]
  // ページ数はサーバー(ctx.page_count)と辞書で二重管理のため、範囲外はクランプして守る
  const page = Math.min(Math.max(ctx.page, 0), pages.length - 1)
  const { title, lines } = pages[page]

  return (
    <div className="retro-screen">
      <RetroFrame
        style={{
          width: '64vw',
          minHeight: '52vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '2vh',
        }}
      >
        <h2 className="retro-heading" style={{ fontSize: '2.8vw' }}>
          {title}
        </h2>
        <div className="retro-text" style={{ textAlign: 'center' }}>
          {lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1vh' }}>
          <PageDots page={page} pageCount={ctx.page_count} />
          <div className="retro-text" style={{ fontSize: '1.3vw', color: 'var(--neon-base)' }}>
            {t(lang, 'rulePageNav')} / {t(lang, 'ruleClose')}
          </div>
        </div>
      </RetroFrame>
    </div>
  )
}
