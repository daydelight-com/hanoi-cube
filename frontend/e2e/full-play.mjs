// E2E: モックCVで一連のプレイを通しで踏む(S5 DoD の無人検証)。
//
// 前提: `make dev` が起動済み(サーバー:8000+フロント:5173。Vite が /ws /api を
// プロキシする)。ディスプレイは Chromium、コントローラは iPad 相当の
// WebKit(タッチ操作)で開く。実行:
//   node e2e/full-play.mjs [--out <スクリーンショット出力先>]
//
// 注意: 本番60秒タイマーを実時間で待つため、全体で約90秒かかる。

import { mkdirSync } from 'node:fs'
import { chromium, devices, webkit } from 'playwright'

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:5173'
const outIdx = process.argv.indexOf('--out')
const OUT = outIdx >= 0 ? process.argv[outIdx + 1] : null
if (OUT) mkdirSync(OUT, { recursive: true })

const IPAD = devices['iPad (gen 11)'] ?? devices['iPad (gen 7)']
if (!IPAD) throw new Error('Playwright の iPad デバイス定義が見つからない')

let step = 0
async function shot(page, name) {
  if (!OUT) return
  step += 1
  await page.screenshot({ path: `${OUT}/${String(step).padStart(2, '0')}-${name}.png` })
}

async function waitText(page, text, timeout = 10_000) {
  await page.getByText(text, { exact: false }).first().waitFor({ state: 'visible', timeout })
}

async function setBoard(page, board) {
  const res = await page.evaluate(async (b) => {
    const r = await fetch('/api/mock/board', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ board: b }),
    })
    return r.status
  }, board)
  if (res !== 200) throw new Error(`mock board API failed: ${res}`)
  await page.waitForTimeout(300) // 確定盤面の配信を待つ
}

const displayBrowser = await chromium.launch()
const padBrowser = await webkit.launch()
try {
  const display = await displayBrowser.newPage({ viewport: { width: 1920, height: 1080 } })
  await display.goto(BASE + '/')

  // iPad 実機 Safari 相当(WebKit + iPad ビューポート + タッチ)
  const padCtx = await padBrowser.newContext({ ...IPAD })
  const pad = await padCtx.newPage()
  await pad.goto(BASE + '/controller')

  const ok = () => pad.tap('.pad-button--enter')
  const left = () => pad.tap('.pad-buttons .pad-button--arrow >> nth=0')
  const right = () => pad.tap('.pad-buttons .pad-button--arrow >> nth=1')

  // 1. 待機画面(起動直後前提。タイトル⇄ランキングのどちらで掴んでもよい)
  await display
    .getByText('けっていボタンで スタート')
    .or(display.getByText('ランキング'))
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  if (!(await display.getByText('けっていボタンで スタート').isVisible())) {
    await ok() // idle_ranking → idle_title(screens.md 行4)
    await waitText(display, 'けっていボタンで スタート')
  }
  await shot(display, 'idle-title')
  await shot(pad, 'pad-buttons')

  // ディスプレイ側の実ユーザー操作でAudioContextをアンロックする。
  // 画面操作はiPad側なので、このクリック自体はゲーム状態を変えない。
  await display.locator('.retro-root').click({ position: { x: 20, y: 20 } })

  // 2. タイトル → モード選択
  await ok()
  await waitText(display, 'モードをえらんでね')

  // 3. 練習へ(rules → practice)。モード選択の項目名と紛れないようヒント文で確認
  await right()
  await ok()
  await waitText(display, 'はこを ならべて けっていで はんてい')
  await shot(display, 'practice')

  // 4. 練習で判定(盤面 L// は 1箱×最短1手 = +1)
  await setBoard(display, 'L//')
  await ok()
  await waitText(display, '+1')
  await shot(display, 'practice-judge')

  // 5. 練習 → 戻る → モード選択
  await left()
  await ok()
  await waitText(display, 'モードをえらんでね')

  // 6. 本番へ(rules → practice → game)。カウントダウン 3,2,1,GO
  await right()
  await right()
  await ok()
  await display.waitForSelector('.retro-countdown', { timeout: 5_000 })
  await shot(display, 'countdown')
  await waitText(display, 'GO!', 5_000)

  // 7. 計測中: スコア加算(盤面は練習で作った L// のまま。本番開始で判定済み
  //    集合はリセットされるので +1)→ 同一盤面の再判定は「はんていずみ」
  await waitText(display, 'のこり', 5_000)
  await ok()
  await waitText(display, '+1', 5_000)
  await shot(display, 'game-judge')
  await display.waitForTimeout(700) // 判定クールダウン(0.5s)明け
  await ok()
  await waitText(display, 'はんていずみ', 5_000)
  await shot(pad, 'pad-flash-after')

  // 8. タイムアップ → リザルト(実時間で残りを待つ)
  await waitText(display, 'けっか はっぴょう', 70_000)
  await shot(display, 'result-typing')

  // 9. 名前入力(iPad にキーボードが出る)→ 完了 → 決定
  await pad.waitForSelector('.pad-name-input', { timeout: 5_000 })
  await shot(pad, 'pad-name')
  await pad.fill('.pad-name-input', 'テスト')
  await waitText(display, 'テスト') // ディスプレイへのミラー
  await pad.tap('.pad-button--done')
  await pad.waitForSelector('.pad-button--enter', { timeout: 5_000 })
  await shot(display, 'result-buttons')
  await ok() // focus=decide で確定 → ランキング

  // 10. ランキング(3秒ガード後に決定 → QR)
  await waitText(display, 'ランキング')
  await display.waitForSelector('[data-highlight="true"]', { timeout: 5_000 })
  await shot(display, 'ranking')
  await display.waitForTimeout(3_200)
  await ok()

  // 11. QR(QR画像が描画され、5秒ガード後に決定 → タイトル)
  await waitText(display, 'きょうの きろく')
  await display.waitForSelector('img.retro-qr[src^="data:image"]', { timeout: 5_000 })
  await shot(display, 'qr')
  await display.waitForTimeout(5_200)
  await ok()
  await waitText(display, 'けっていボタンで スタート')

  // 12. 効果音の発火検証(S6)。音声出力そのものは無人検証できないため、
  //     エンジンの発火ログ(window.__sfxPlayed)で代替する。実機スピーカーでの
  //     聞こえ方は要人間確認(handoff 参照)
  const displaySfx = await display.evaluate(() => window.__sfxPlayed ?? [])
  const padSfx = await pad.evaluate(() => window.__sfxPlayed ?? [])
  const countOf = (log, id) => log.filter((x) => x === id).length
  // 台本から一意に決まる回数は厳密に、操作タイミング依存のものは1回以上で検証
  // judge_success は練習(+1)と本番(+1)の2回
  const exactDisplay = { count: 3, go: 1, timeup: 1, tick10: 9, judge_success: 2, judge_dup: 1 }
  const atLeastDisplay = ['decide', 'cursor', 'back', 'key_touch']
  const problems = []
  for (const [id, n] of Object.entries(exactDisplay)) {
    if (countOf(displaySfx, id) !== n)
      problems.push(`display ${id}=${countOf(displaySfx, id)} (期待${n})`)
  }
  for (const id of atLeastDisplay) {
    if (countOf(displaySfx, id) < 1) problems.push(`display ${id} 未発火`)
  }
  for (const id of ['pad_button', 'pad_flash']) {
    if (countOf(padSfx, id) < 1) problems.push(`pad ${id} 未発火`)
  }
  if (problems.length > 0) throw new Error(`効果音の発火検証に失敗: ${problems.join(', ')}`)
  console.log(`sfx: display=${displaySfx.length}発火 pad=${padSfx.length}発火 (検証OK)`)

  // 13. BGMの画面フェーズ連動に加え、手順1のクリックでAudioContextが実際に起動し、
  //     各曲のノートをスケジュールしたことも検証する。
  const bgmHistory = await display.evaluate(() => window.__bgmHistory ?? [])
  const expectedBgm = ['waiting', null, 'gameplay', 'result', 'waiting']
  if (JSON.stringify(bgmHistory) !== JSON.stringify(expectedBgm)) {
    throw new Error(`BGM切替履歴が不正: ${JSON.stringify(bgmHistory)}`)
  }
  const bgmPlayback = await display.evaluate(() => window.__bgm?.playbackState)
  const expectedStarted = ['waiting', 'gameplay', 'result', 'waiting']
  if (
    bgmPlayback?.context !== 'running' ||
    bgmPlayback.activeTrack !== 'waiting' ||
    bgmPlayback.scheduledNotes < 1 ||
    JSON.stringify(bgmPlayback.startedTracks) !== JSON.stringify(expectedStarted)
  ) {
    throw new Error(`BGM再生エンジンが不正: ${JSON.stringify(bgmPlayback)}`)
  }
  console.log(`bgm: ${bgmHistory.map((id) => id ?? 'countdown-silence').join(' → ')} (検証OK)`)

  console.log('E2E full play: PASS')
} finally {
  await displayBrowser.close()
  await padBrowser.close()
}
