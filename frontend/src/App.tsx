import { ControllerApp } from './controller/ControllerApp'
import { DisplayApp } from './display/DisplayApp'

// パスでアプリを切り替える(SPAフォールバック)。/controller = iPadコントローラ、
// それ以外はディスプレイ。管理画面(/admin)は S10 で追加する。
function App() {
  if (location.pathname.startsWith('/controller')) return <ControllerApp />
  return <DisplayApp />
}

export default App
