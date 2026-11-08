import { useEffect, useRef } from 'react'

/**
 * Calls `fn` immediately and then every `ms`, but only while the document is visible.
 * Overlapping calls are skipped (a slow backend never builds a request backlog) and everything is cleaned up on unmount.
 */
export function usePolling(fn: () => Promise<unknown> | void, ms: number, enabled = true) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!enabled) return
    let stop = false
    let busy = false
    const run = async () => {
      if (stop || busy || document.hidden) return
      busy = true
      try { await ref.current() } catch { /* callers handle their own errors */ } finally { busy = false }
    }
    run()
    const id = window.setInterval(run, ms)
    const vis = () => { if (!document.hidden) run() }
    document.addEventListener('visibilitychange', vis)
    return () => { stop = true; window.clearInterval(id); document.removeEventListener('visibilitychange', vis) }
  }, [ms, enabled])
}
