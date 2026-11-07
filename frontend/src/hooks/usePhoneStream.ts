import { useEffect, useRef, useCallback } from 'react'
import { createControlSocket, sendControl } from '../services/websocket'
import type { ControlCommand } from '../types'

export function usePhoneStream(
  deviceId: string,
  _canvasRef?: React.RefObject<HTMLCanvasElement | null>,
) {
  const controlWs = useRef<WebSocket | null>(null)

  useEffect(() => {
    const control = createControlSocket(deviceId)
    controlWs.current = control

    return () => {
      control.close()
      controlWs.current = null
    }
  }, [deviceId])

  const send = useCallback((cmd: ControlCommand) => {
    if (controlWs.current) sendControl(controlWs.current, cmd)
  }, [])

  return { send }
}
