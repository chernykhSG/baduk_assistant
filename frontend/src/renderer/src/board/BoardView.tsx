import { Goban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition } from '../state/appState'

export function BoardView() {
  const position = currentBoardPosition.value

  if (!position) {
    return <div class="board-view board-view--empty">Откройте SGF-файл, чтобы начать</div>
  }

  return <Goban signMap={position.signMap} vertexSize={24} />
}
