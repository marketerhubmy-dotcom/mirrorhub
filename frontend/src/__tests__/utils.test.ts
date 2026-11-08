import { describe, expect, it } from 'vitest'
import { containedContentRect, toRelative } from '../utils/geometry'
import { codecFromSps, nalOffsets } from '../hooks/useDeviceStream'
import { fmtBytes } from '../services/deviceApi'

describe('containedContentRect', () => {
  it('letterboxes a portrait phone inside a wide tile (the real Pixel tile: 710x614, video 432x960)', () => {
    const r = containedContentRect({ left: 980, top: 106, width: 710, height: 614 }, 432, 960)
    expect(Math.round(r.width)).toBe(276)
    expect(Math.round(r.height)).toBe(614)
    expect(Math.round(r.left)).toBe(980 + Math.round((710 - 276.3) / 2))
  })
  it('falls back to the element when sizes are unknown', () => {
    const el = { left: 1, top: 2, width: 3, height: 4 }
    expect(containedContentRect(el, 0, 0)).toEqual(el)
    expect(containedContentRect({ ...el, width: 0 }, 10, 10).width).toBe(0)
  })
})

describe('toRelative', () => {
  const c = { left: 100, top: 50, width: 200, height: 400 }
  it('maps inside points to 0..1', () => {
    expect(toRelative(c, 200, 250)).toEqual({ x: 0.5, y: 0.5 })
    expect(toRelative(c, 100, 50)).toEqual({ x: 0, y: 0 })
  })
  it('rejects points in the letterbox bars (a click there must not become a tap)', () => {
    expect(toRelative(c, 99, 100)).toBeNull()
    expect(toRelative(c, 301, 100)).toBeNull()
    expect(toRelative(c, 150, 451)).toBeNull()
  })
  it('rejects non-finite results', () => {
    expect(toRelative({ left: 0, top: 0, width: 0, height: 0 }, 1, 1)).toBeNull()
  })
})

describe('H.264 helpers', () => {
  it('builds the WebCodecs codec string from the SPS (real Pixel SPS 67 64 00 1f)', () => {
    const sps = new Uint8Array([0, 0, 0, 1, 0x67, 0x64, 0x00, 0x1f, 0xac])
    expect(codecFromSps(sps)).toBe('avc1.64001f')
  })
  it('finds every NAL with its type, including back-to-back SPS/PPS/IDR', () => {
    const au = new Uint8Array([0, 0, 0, 1, 0x67, 1, 2, 0, 0, 0, 1, 0x68, 3, 0, 0, 0, 1, 0x65, 9, 9])
    expect(nalOffsets(au)).toEqual([[0, 7], [7, 8], [13, 5]])
  })
  it('does not invent NALs in data without start codes', () => {
    expect(nalOffsets(new Uint8Array([1, 2, 3, 4, 5, 6]))).toEqual([])
  })
})

describe('fmtBytes', () => {
  it.each([[0, '0 B'], [1023, '1023 B'], [1024, '1.0 KB'], [1048576 * 5.5, '5.5 MB'], [1073741824 * 200, '200 GB']])('%s -> %s', (n, s) => {
    expect(fmtBytes(n)).toBe(s)
  })
})
