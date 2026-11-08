import { useEffect, useRef, useState } from 'react'

/**
 * Embedded live video for ONE device (docs/DECISIONS.md ADR-002).
 *
 * Server protocol (/ws/video/{id}?profile=...):
 *   binary message = one H.264 NAL unit with a 4-byte Annex-B start code
 *   text message   = JSON {event:'state'|'error', state?, error?}
 * Decoded with WebCodecs (Annex-B mode: no `description`) onto a <canvas>.
 *
 * NOT verified against a physical phone yet — see docs/QA_MATRIX.md #6.
 */

export type StreamProfile = 'thumb' | 'normal' | 'focus'
export type StreamState =
  | 'paused' | 'connecting' | 'starting' | 'streaming' | 'reconnecting' | 'failed' | 'stopped' | 'unsupported'

export interface StreamStats {
  fps: number
  kbps: number
  width: number
  height: number
}

const MAX_DECODE_QUEUE = 30

export function codecFromSps(sps: Uint8Array): string {
  // sps[4] is the NAL header; profile_idc, constraint flags, level_idc follow.
  const hex = (n: number) => n.toString(16).padStart(2, '0')
  return `avc1.${hex(sps[5])}${hex(sps[6])}${hex(sps[7])}`
}

/** [offset-of-start-code, nal_type] for every NAL in a picture (4-byte start codes). */
export function nalOffsets(au: Uint8Array): [number, number][] {
  const out: [number, number][] = []
  for (let i = 0; i + 4 < au.length; i++) {
    if (au[i] === 0 && au[i + 1] === 0 && au[i + 2] === 0 && au[i + 3] === 1) { out.push([i, au[i + 4] & 0x1f]); i += 3 }
  }
  return out
}

function sameBytes(a: Uint8Array | null, b: Uint8Array): boolean {
  if (!a || a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

export function useDeviceStream(
  deviceId: string,
  profile: StreamProfile,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  paused = false,
) {
  const [state, setState] = useState<StreamState>(paused ? 'paused' : 'connecting')
  const [error, setError] = useState('')
  const [stats, setStats] = useState<StreamStats>({ fps: 0, kbps: 0, width: 0, height: 0 })
  const statsRef = useRef({ frames: 0, bytes: 0 })
  // cumulative decoder counters, reported to the Performance dashboard (received / decoded / dropped)
  const totalsRef = useRef({ received: 0, decoded: 0, dropped: 0 })

  useEffect(() => {
    if (paused) {
      setState('paused')
      setStats((s) => ({ ...s, fps: 0, kbps: 0 }))
      return
    }
    const canvas = canvasRef.current
    if (!canvas) return
    if (typeof VideoDecoder === 'undefined') {
      setState('unsupported')
      setError('WebCodecs tidak disokong oleh webview ini')
      return
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let disposed = false
    let ws: WebSocket | null = null
    let retry = 0
    let retryTimer: number | undefined
    let decoder: VideoDecoder | null = null
    let sps: Uint8Array | null = null
    let needConfigure = true
    let haveKey = false
    let tsUs = 0

    const makeDecoder = () => {
      decoder = new VideoDecoder({
        output: (frame) => {
          if (canvas.width !== frame.displayWidth) canvas.width = frame.displayWidth
          if (canvas.height !== frame.displayHeight) canvas.height = frame.displayHeight
          ctx.drawImage(frame, 0, 0)
          frame.close()
          statsRef.current.frames++
          totalsRef.current.decoded++
          setState((s) => (s === 'streaming' ? s : 'streaming'))
        },
        error: (e) => {
          // A decoder error closes it: rebuild and wait for the next keyframe.
          setError(`decoder: ${e.message}`)
          haveKey = false
          needConfigure = true
          decoder = null
          totalsRef.current.dropped++
        },
      })
    }

    // One message = one picture: NAL units each preceded by a 4-byte start code.
    // Keyframe pictures always carry SPS+PPS (guaranteed by the server hub).
    const handleAu = (au: Uint8Array) => {
      statsRef.current.bytes += au.length
      totalsRef.current.received++
      let isKey = false
      let hasVcl = false
      for (const [start, type] of nalOffsets(au)) {
        if (type === 7) {
          let end = au.length
          for (const [s2] of nalOffsets(au)) if (s2 > start) { end = s2; break }
          const nal = au.subarray(start, end)
          if (!sameBytes(sps, nal)) { sps = nal.slice(); needConfigure = true }  // e.g. rotation
        } else if (type === 5) { isKey = true; hasVcl = true }
        else if (type === 1) hasVcl = true
      }
      if (!hasVcl) return

      if (!decoder || decoder.state === 'closed') { makeDecoder(); needConfigure = true }
      const dec = decoder!
      if (isKey) {
        if (!sps) return
        if (needConfigure || dec.state !== 'configured') {
          try {
            dec.configure({ codec: codecFromSps(sps), optimizeForLatency: true })
          } catch (e) {
            setError(`configure: ${(e as Error).message}`)
            return
          }
          needConfigure = false
        }
        haveKey = true
        dec.decode(new EncodedVideoChunk({ type: 'key', timestamp: (tsUs += 33_333), data: au }))
      } else {
        if (!haveKey || dec.state !== 'configured') { totalsRef.current.dropped++; return }
        if (dec.decodeQueueSize > MAX_DECODE_QUEUE) { haveKey = false; totalsRef.current.dropped++; return }  // too far behind: resync at next IDR
        dec.decode(new EncodedVideoChunk({ type: 'delta', timestamp: (tsUs += 33_333), data: au }))
      }
    }

    const connect = () => {
      if (disposed) return
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      ws = new WebSocket(`${proto}//${window.location.host}/ws/video/${encodeURIComponent(deviceId)}?profile=${profile}`)
      ws.binaryType = 'arraybuffer'
      setState(retry === 0 ? 'connecting' : 'reconnecting')

      ws.onopen = () => { retry = 0 }
      ws.onmessage = (e) => {
        if (typeof e.data === 'string') {
          try {
            const msg = JSON.parse(e.data)
            if (msg.event === 'error') { setState('failed'); setError(msg.error ?? '') }
            else if (msg.event === 'state') {
              setError(msg.error ?? '')
              if (msg.state !== 'streaming') setState(msg.state as StreamState)
              else setState((s) => (s === 'streaming' ? s : 'starting'))
            }
          } catch { /* ignore malformed status */ }
          return
        }
        handleAu(new Uint8Array(e.data as ArrayBuffer))
      }
      ws.onclose = (e) => {
        if (disposed) return
        if (e.code === 4400 || e.code === 4403 || e.code === 4404) { setState('failed'); return }  // not retryable
        setState('reconnecting')
        haveKey = false
        retry++
        retryTimer = window.setTimeout(connect, Math.min(1000 * 2 ** Math.min(retry, 3), 8000))
      }
    }
    connect()

    let tick = 0
    totalsRef.current = { received: 0, decoded: 0, dropped: 0 }
    const statsTimer = window.setInterval(() => {
      const { frames, bytes } = statsRef.current
      statsRef.current = { frames: 0, bytes: 0 }
      setStats({ fps: frames, kbps: Math.round((bytes * 8) / 1000), width: canvas.width, height: canvas.height })
      // every 5 s tell the backend what this tile's decoder really did (visible hidden tabs report nothing)
      if (++tick % 5 === 0 && !document.hidden && totalsRef.current.received > 0) {
        fetch('/api/v1/perf/client-stats', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
          body: JSON.stringify({ device_id: deviceId, profile, ...totalsRef.current, fps: frames, width: canvas.width, height: canvas.height }),
        }).catch(() => { /* telemetry is best-effort */ })
      }
    }, 1000)

    return () => {
      disposed = true
      window.clearTimeout(retryTimer)
      window.clearInterval(statsTimer)
      ws?.close()
      if (decoder && decoder.state !== 'closed') decoder.close()
    }
  }, [deviceId, profile, paused, canvasRef])

  return { state, error, stats }
}
