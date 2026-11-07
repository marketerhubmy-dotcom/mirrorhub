import { useRef } from 'react'
import type { ControlCommand } from '../types'

interface Props {
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  onCommand: (cmd: ControlCommand) => void
}

interface PressState {
  x: number
  y: number
  time: number
}

export default function PhoneScreen({ canvasRef, onCommand }: Props) {
  const pressRef = useRef<PressState | null>(null)

  const getRelative = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height,
    }
  }

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const pos = getRelative(e)
    pressRef.current = { ...pos, time: Date.now() }
  }

  const onMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!pressRef.current) return
    const start = pressRef.current
    const end = getRelative(e)
    const duration = Date.now() - start.time
    const moved = Math.abs(end.x - start.x) > 0.02 || Math.abs(end.y - start.y) > 0.02

    if (moved) {
      onCommand({ type: 'swipe', x1: start.x, y1: start.y, x2: end.x, y2: end.y })
    } else if (duration >= 500) {
      onCommand({ type: 'long_press', x: start.x, y: start.y })
    } else {
      onCommand({ type: 'tap', x: start.x, y: start.y })
    }

    pressRef.current = null
  }

  return (
    <div className="flex items-center justify-center bg-black rounded-xl overflow-hidden min-h-48">
      <canvas
        ref={canvasRef as React.RefObject<HTMLCanvasElement>}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { pressRef.current = null }}
        className="max-w-full max-h-[65vh] cursor-pointer select-none"
      />
    </div>
  )
}
