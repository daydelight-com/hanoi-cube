import { DisplayApp } from './display/DisplayApp'

// S3時点はディスプレイ表示のみ。iPadコントローラ(/controller)・管理画面は
// 以降のセッションでルーティングを足す。
function App() {
  return <DisplayApp />
}

export default App
