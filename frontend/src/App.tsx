import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import DevicePage from './pages/DevicePage'
import AutomationPage from './pages/AutomationPage'
import ContentStudioPage from './pages/ContentStudioPage'
import ExecutionMonitorPage from './pages/ExecutionMonitorPage'
import VisionDebuggerPage from './pages/VisionDebuggerPage'
import WorkflowManagerPage from './pages/WorkflowManagerPage'
import WorkflowEditorPage from './pages/WorkflowEditorPage'
import WorkflowRecorderPage from './pages/WorkflowRecorderPage'
import TikTokPublisherPage from './pages/TikTokPublisherPage'
import CampaignManagerPage from './pages/CampaignManagerPage'
import QueueManagerPage from './pages/QueueManagerPage'
import AboutPage from './pages/AboutPage'
import SettingsPage from './pages/SettingsPage'
import DeviceWallPage from './pages/DeviceWallPage'
import OrchestratorPage from './pages/OrchestratorPage'
import AIControlCenterPage from './pages/AIControlCenterPage'
import PipelinePage from './pages/PipelinePage'
import QuickLaunchPage from './pages/QuickLaunchPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/device/:deviceId" element={<DevicePage />} />
        <Route path="/automation" element={<AutomationPage />} />
        <Route path="/content" element={<ContentStudioPage />} />
        <Route path="/execution" element={<ExecutionMonitorPage />} />
        <Route path="/vision" element={<VisionDebuggerPage />} />
        <Route path="/workflows" element={<WorkflowManagerPage />} />
        <Route path="/workflows/:id/edit" element={<WorkflowEditorPage />} />
        <Route path="/workflows/record" element={<WorkflowRecorderPage />} />
        <Route path="/tiktok" element={<TikTokPublisherPage />} />
        <Route path="/campaigns" element={<CampaignManagerPage />} />
        <Route path="/queue" element={<QueueManagerPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/device-wall" element={<DeviceWallPage />} />
        <Route path="/orchestrator" element={<OrchestratorPage />} />
        <Route path="/ai" element={<AIControlCenterPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/quicklaunch" element={<QuickLaunchPage />} />
      </Routes>
    </BrowserRouter>
  )
}
