import type { ControlCommand } from '../types'

function wsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

export function createViewSocket(
  deviceId: string,
  onFrame: (data: ArrayBuffer) => void,
): WebSocket {
  const ws = new WebSocket(wsUrl(`/ws/view/${deviceId}`))
  ws.binaryType = 'arraybuffer'
  ws.onmessage = (e) => onFrame(e.data as ArrayBuffer)
  return ws
}

export function createControlSocket(deviceId: string): WebSocket {
  return new WebSocket(wsUrl(`/ws/control/${deviceId}`))
}

export function sendControl(ws: WebSocket, cmd: ControlCommand): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(cmd))
  }
}
