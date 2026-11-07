import { useRef, useEffect, useState } from 'react'

interface Props {
  deviceId: string
  className?: string
}

export default function DeviceThumbnail({ deviceId, className = '' }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hasFrame, setHasFrame] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/view/${deviceId}`)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = async (e) => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const blob = new Blob([e.data as ArrayBuffer], { type: 'image/jpeg' })
      const bitmap = await createImageBitmap(blob)
      if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
        canvas.width = bitmap.width
        canvas.height = bitmap.height
      }
      ctx.drawImage(bitmap, 0, 0)
      bitmap.close()
      if (!hasFrame) setHasFrame(true)
    }

    return () => ws.close()
  }, [deviceId])

  return (
    <div className={`relative bg-black rounded-lg overflow-hidden ${className}`}
         style={{ aspectRatio: '9/16' }}>
      {!hasFrame && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-xs">
          Connecting...
        </div>
      )}
      <canvas
        ref={canvasRef}
        className="w-full h-full object-contain"
      />
    </div>
  )
}
