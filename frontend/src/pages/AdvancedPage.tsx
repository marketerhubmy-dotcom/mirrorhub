import { Link } from 'react-router-dom'
import { Page } from '../components/AppShell'
import { Card, PageHeader, Pill } from '../components/ui'

const MODULES = [
  { to: '/quicklaunch', title: 'Quick Launch', desc: 'Jalankan aliran kerja pantas pada telefon pilihan.' },
  { to: '/pipeline', title: 'AI Video Studio', desc: 'Saluran kandungan YT Create → TikTok.' },
  { to: '/content', title: 'Content Studio', desc: 'Penjanaan kandungan dengan AI (perlu OPENAI_API_KEY).' },
  { to: '/tiktok', title: 'TikTok Publisher', desc: 'Penerbitan TikTok melalui automasi UI.' },
  { to: '/campaigns', title: 'Campaigns', desc: 'Pengurus kempen dan jadual.' },
  { to: '/queue', title: 'Queue', desc: 'Baris gilir pelaksanaan.' },
  { to: '/workflows', title: 'Workflows', desc: 'Perakam dan editor aliran kerja.' },
  { to: '/vision', title: 'Vision', desc: 'Penyahpepijat analisis skrin.' },
  { to: '/execution', title: 'Execution Monitor', desc: 'Pemantau pelaksanaan langkah.' },
  { to: '/orchestrator', title: 'Orchestrator', desc: 'Kesihatan armada dan failover.' },
  { to: '/ai', title: 'AI Agent', desc: 'Lapisan ejen AI.' },
  { to: '/about', title: 'Tentang', desc: 'Versi dan maklumat binaan.' },
]

export default function AdvancedPage() {
  return (
    <Page>
      <PageHeader title="Modul lanjutan" subtitle="Automasi, kandungan dan kempen. Modul ini wujud sebelum Desktop V1 dan belum melalui pengesahan perkakasan yang sama seperti Peranti/Wall." />
      <div className="grid gap-3 sm:grid-cols-2">
        {MODULES.map((m) => (
          <Link key={m.to} to={m.to}>
            <Card className="p-4 h-full hover:border-brand-500/60 transition-colors">
              <div className="flex items-center gap-2 mb-1"><h3 className="font-medium text-white">{m.title}</h3><Pill>lanjutan</Pill></div>
              <p className="text-xs text-gray-400">{m.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </Page>
  )
}
