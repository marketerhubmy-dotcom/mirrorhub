export interface Device {
  device_id: string
  device_name: string
  battery: number
  wifi: boolean
  is_online: boolean
  adb_address: string | null
  last_seen: string
}

export interface MirrorStatus {
  device_id: string
  mirroring: boolean
}

export type ControlCommand =
  | { type: 'tap'; x: number; y: number }
  | { type: 'long_press'; x: number; y: number }
  | { type: 'swipe'; x1: number; y1: number; x2: number; y2: number }
  | { type: 'text'; value: string }
  | { type: 'key'; code: string }
  | { type: 'nav'; action: 'home' | 'back' | 'recents' }
