import type { ControlCommand } from '../types'

interface Props {
  onCommand: (cmd: ControlCommand) => void
}

const BUTTONS: { label: string; action: 'back' | 'home' | 'recents' }[] = [
  { label: 'Back', action: 'back' },
  { label: 'Home', action: 'home' },
  { label: 'Recents', action: 'recents' },
]

export default function NavControls({ onCommand }: Props) {
  return (
    <div className="flex gap-2">
      {BUTTONS.map(({ label, action }) => (
        <button
          key={action}
          onClick={() => onCommand({ type: 'nav', action })}
          className="flex-1 py-2.5 rounded-lg bg-gray-800 text-white text-sm font-medium
            hover:bg-gray-700 active:scale-95 transition-all select-none"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
