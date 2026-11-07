export interface Rect { left: number; top: number; width: number; height: number }

/**
 * The area actually covered by video inside an element that letterboxes it
 * (CSS object-fit: contain) — pointer coordinates must be mapped against this,
 * not against the whole element, or taps land in the wrong place.
 */
export function containedContentRect(el: Rect, videoW: number, videoH: number): Rect {
  if (videoW <= 0 || videoH <= 0 || el.width <= 0 || el.height <= 0) return el
  const scale = Math.min(el.width / videoW, el.height / videoH)
  const width = videoW * scale
  const height = videoH * scale
  return { left: el.left + (el.width - width) / 2, top: el.top + (el.height - height) / 2, width, height }
}

/** Map a client point to 0..1 inside `content`; null when outside it. */
export function toRelative(content: Rect, clientX: number, clientY: number): { x: number; y: number } | null {
  const x = (clientX - content.left) / content.width
  const y = (clientY - content.top) / content.height
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x, y }
}
