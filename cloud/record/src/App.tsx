// 記録画面(仕様§5.10)。URL /records/{play_id} で1プレイの記録を表示する。
// アップロード前にQRが読まれた場合は「準備中」(ドキュメント不存在)を表示する。

import { useEffect, useState } from 'react'
import './App.css'
import { JudgementCard } from './components/JudgementCard'
import { fetchPlay, type FetchResult } from './fetchPlay'

type ViewState = { kind: 'loading' } | { kind: 'error' } | { kind: 'invalid_url' } | FetchState
type FetchState =
  { kind: 'ok'; play: FetchResultPlay } | { kind: 'not_found' } | { kind: 'unconfigured' }
type FetchResultPlay = Extract<FetchResult, { status: 'ok' }>['play']

function playIdFromPath(pathname: string): string | null {
  const match = /^\/records\/([\w-]+)$/.exec(pathname)
  return match ? match[1] : null
}

function formatPlayedAt(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

function toViewState(result: FetchResult): ViewState {
  if (result.status === 'ok') return { kind: 'ok', play: result.play }
  if (result.status === 'not_found') return { kind: 'not_found' }
  return { kind: 'unconfigured' }
}

export default function App() {
  const playId = playIdFromPath(window.location.pathname)
  const [state, setState] = useState<ViewState>(
    playId === null ? { kind: 'invalid_url' } : { kind: 'loading' },
  )
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (playId === null) return
    let cancelled = false
    fetchPlay(playId)
      .then((result) => {
        if (!cancelled) setState(toViewState(result))
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [playId, attempt])

  // 「もういちど よみこむ」: loading に戻して再取得(準備中の再確認にも使う)
  const load = () => {
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }

  return (
    <div className="app">
      {/* ゲーム画面と同じCRTスキャンライン(最前面・操作は透過) */}
      <div className="retro-scanlines" aria-hidden="true" />
      <header className="app-header">
        <h1>Cubeでハノイ</h1>
        <p className="app-subtitle">プレイきろく</p>
      </header>
      {state.kind === 'loading' && <p className="app-status">よみこみちゅう…</p>}
      {state.kind === 'invalid_url' && <p className="app-status">URLが ただしくありません</p>}
      {state.kind === 'unconfigured' && (
        <p className="app-status">この ページは まだ せっていちゅうです(Firebase 設定なし)</p>
      )}
      {state.kind === 'error' && (
        <div className="app-status">
          <p>よみこみに しっぱいしました</p>
          <button type="button" className="card-action" onClick={load}>
            もういちど よみこむ
          </button>
        </div>
      )}
      {state.kind === 'not_found' && (
        <div className="app-status">
          <p className="app-preparing">じゅんびちゅう…</p>
          <p>きろくを アップロードしています。すこし まってから ひらいてね</p>
          <button type="button" className="card-action" onClick={load}>
            もういちど よみこむ
          </button>
        </div>
      )}
      {state.kind === 'ok' && <PlayView play={state.play} />}
    </div>
  )
}

function PlayView({ play }: { play: FetchResultPlay }) {
  return (
    <main>
      <section className="summary">
        <p className="summary-name">{play.player_name} さん</p>
        <p className="summary-score">
          {play.score} <span className="summary-unit">てん</span>
        </p>
        <p className="summary-meta">
          しっぱい {play.fail_count} かい ・ {formatPlayedAt(play.played_at)}
        </p>
      </section>
      <section className="cards">
        <h2 className="cards-heading">はんてい の きろく({play.judgements.length}かい)</h2>
        {play.judgements.map((judgement) => (
          <JudgementCard key={judgement.seq} judgement={judgement} />
        ))}
        {play.judgements.length === 0 && <p className="app-status">はんてい は ありませんでした</p>}
      </section>
      <footer className="app-footer">PyCon JP 2026 ブースゲーム「Cubeでハノイ」</footer>
    </main>
  )
}
