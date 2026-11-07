/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react'

type TypedArray = Uint8Array<ArrayBuffer>

function getNalType(unit: TypedArray): number {
  const offset = unit[2] === 0 && unit[3] === 1 ? 4 : 3
  return (unit[offset] ?? 0) & 0x1f
}

function splitNals(data: TypedArray): TypedArray[] {
  const starts: number[] = []
  for (let i = 0; i < data.length - 3; i++) {
    if (data[i] === 0 && data[i + 1] === 0) {
      if (data[i + 2] === 0 && data[i + 3] === 1) { starts.push(i); i += 3 }
      else if (data[i + 2] === 1) { starts.push(i); i += 2 }
    }
  }
  return starts.map((s, j): TypedArray => {
    const end = j + 1 < starts.length ? starts[j + 1] : data.length
    return Uint8Array.from(data.subarray(s, end)) as TypedArray
  })
}

function buildAvcC(spsUnit: TypedArray, ppsUnit: TypedArray): ArrayBuffer {
  const sps = Uint8Array.from(spsUnit.subarray(spsUnit[2] === 0 ? 4 : 3)) as TypedArray
  const pps = Uint8Array.from(ppsUnit.subarray(ppsUnit[2] === 0 ? 4 : 3)) as TypedArray
  const buf = new Uint8Array(11 + sps.length + pps.length) as TypedArray
  let i = 0
  buf[i++] = 1; buf[i++] = sps[1]; buf[i++] = sps[2]; buf[i++] = sps[3]
  buf[i++] = 0xff; buf[i++] = 0xe1
  buf[i++] = (sps.length >> 8) & 0xff; buf[i++] = sps.length & 0xff
  buf.set(sps, i); i += sps.length
  buf[i++] = 1
  buf[i++] = (pps.length >> 8) & 0xff; buf[i++] = pps.length & 0xff
  buf.set(pps, i)
  return buf.buffer as ArrayBuffer
}

export function useH264Stream(
  deviceId: string,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
) {
  const decoderRef = useRef<VideoDecoder | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    if (!('VideoDecoder' in window)) {
      console.warn('WebCodecs not supported')
      return
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let sps: TypedArray | null = null
    let pps: TypedArray | null = null
    let configured = false
    let ts = 0
    let buffer: TypedArray = new Uint8Array(0) as TypedArray

    const decoder = new VideoDecoder({
      output: (frame) => {
        if (canvas.width !== frame.displayWidth) canvas.width = frame.displayWidth
        if (canvas.height !== frame.displayHeight) canvas.height = frame.displayHeight
        ctx.drawImage(frame, 0, 0)
        frame.close()
      },
      error: () => { configured = false },
    })
    decoderRef.current = decoder

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}/ws/video/${deviceId}`)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (e) => {
      const incoming = new Uint8Array(e.data as ArrayBuffer) as TypedArray
      const combined = new Uint8Array(buffer.length + incoming.length) as TypedArray
      combined.set(buffer as any); combined.set(incoming as any, buffer.length)
      buffer = combined

      const units = splitNals(buffer)
      if (units.length < 2) return

      for (let i = 0; i < units.length - 1; i++) {
        const unit = units[i]
        const type = getNalType(unit)

        if (type === 7) { sps = unit; configured = false }
        else if (type === 8) { pps = unit }
        else if ((type === 5 || type === 1) && sps && pps) {
          if (!configured && decoder.state !== 'closed') {
            try {
              const s = Uint8Array.from(sps.subarray(sps[2] === 0 ? 4 : 3)) as TypedArray
              const codec = `avc1.${s[1].toString(16).padStart(2, '0')}${s[2].toString(16).padStart(2, '0')}${s[3].toString(16).padStart(2, '0')}`
              decoder.configure({ codec, description: buildAvcC(sps, pps), optimizeForLatency: true })
              configured = true
            } catch { return }
          }
          if (configured && decoder.state === 'configured') {
            try {
              const copy = Uint8Array.from(unit) as TypedArray
              decoder.decode(new EncodedVideoChunk({
                type: type === 5 ? 'key' : 'delta',
                timestamp: ts++,
                data: copy.buffer as ArrayBuffer,
              }))
            } catch { configured = false }
          }
        }
      }

      buffer = units.length > 0 ? units[units.length - 1] : (new Uint8Array(0) as TypedArray)
    }

    return () => {
      ws.close()
      if (decoder.state !== 'closed') decoder.close()
      decoderRef.current = null
    }
  }, [deviceId, canvasRef])
}
