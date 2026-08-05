// レトロUIの共通コンポーネント。フォーカス・ページ等の状態はすべてサーバー配信の
// ctx に従う(ディスプレイは表示専用。ws-messages.md)。

import type { ReactNode } from 'react'
import './retro.css'

/** 点滅テキスト(PRESS ENTER 等) */
export function Blink({ children }: { children: ReactNode }) {
  return <span className="retro-blink">{children}</span>
}

/** ネオン枠パネル(ダイアログ・パネル共通) */
export function RetroFrame({
  children,
  className,
  style,
}: {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div className={`retro-frame${className ? ` ${className}` : ''}`} style={style}>
      {children}
    </div>
  )
}

/** メニュー項目。focused はサーバーの ctx.focus に追従する */
export function MenuItem({ focused, children }: { focused: boolean; children: ReactNode }) {
  return (
    <div className={`retro-menu-item${focused ? ' retro-menu-item--focused' : ''}`}>{children}</div>
  )
}

/** ページインジケーター(●○○) */
export function PageDots({ page, pageCount }: { page: number; pageCount: number }) {
  return (
    <div className="retro-page-dots" aria-label={`page ${page + 1} / ${pageCount}`}>
      {Array.from({ length: pageCount }, (_, i) => (
        <span key={i} className={i === page ? 'current' : undefined}>
          {i === page ? '●' : '○'}
        </span>
      ))}
    </div>
  )
}
