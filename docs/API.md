# MirrorHub API Reference

Version: 1.0.0  
Base URL: `http://localhost:8000/api/v1`

---

## System

### `GET /system/about`
Full build and version information.

```json
{
  "version": "1.0.0",
  "release_name": "Stable",
  "build_date": "2026-07-11",
  "python_version": "3.14.4",
  "platform": "Windows-11...",
  "architecture": "AMD64",
  "plugins": { "youtube_create": "1.0.0", "tiktok": "1.0.0" },
  "modules": { "execution_engine": "1.0.0", ... },
  "database": { "path": "...", "exists": true, "size_bytes": 16384 },
  "server_time": "2026-07-11T00:00:00+00:00"
}
```

### `GET /system/health`
Detailed health check.

```json
{
  "status": "ok",
  "checks": {
    "application": { "ok": true, "detail": "Running" },
    "database": { "ok": true, "detail": "16 KB" },
    "adb": { "ok": true, "detail": "/path/to/adb.exe" },
    "openai": { "ok": true, "detail": "Configured" },
    "disk": { "ok": true, "detail": "45.2 GB free" }
  }
}
```

### `GET /system/settings`
Read-only settings view (API key masked).

---

## Devices

### `GET /devices`
List all registered devices.

### `POST /devices`
Register a device manually.

### `GET /devices/{device_id}`
Get device by ID.

### `DELETE /devices/{device_id}`
Remove a device.

---

## Mirror

### `POST /mirror/connect`
Connect ADB to a device and register it.

```json
{ "adb_address": "192.168.1.100:37123" }
```

### `POST /mirror/{device_id}/start`
Start scrcpy mirror window.

### `POST /mirror/{device_id}/stop`
Stop the mirror.

---

## Apps — YouTube Create

Base: `/apps/youtube_create`

### `POST /apps/youtube_create/execute`
Execute a YouTube Create job.

```json
{
  "device_id": "uuid",
  "adb_address": "192.168.1.100:37123",
  "video_prompt": "A short ad for...",
  "image_path": "/path/to/image.jpg",
  "post_type": "draft"
}
```

### `POST /apps/youtube_create/simulate`
Dry-run — returns planned steps without executing.

---

## Apps — TikTok Publisher

Base: `/apps/tiktok`

### `POST /apps/tiktok/execute`
Execute a TikTok publish job.

```json
{
  "device_id": "uuid",
  "adb_address": "192.168.1.100:37123",
  "video_path": "C:/videos/clip.mp4",
  "caption": "Check this out",
  "hashtags": ["fyp", "viral"],
  "post_type": "post_now"
}
```

### `POST /apps/tiktok/simulate`
Dry-run — returns planned steps.

### `POST /apps/tiktok/validate`
Validate a job without executing.

### `GET /apps/tiktok/products`
List all products in the TikTok Product Registry.

### `POST /apps/tiktok/products`
Add a product. Returns `201`.

### `PUT /apps/tiktok/products/{id}`
Update a product.

### `DELETE /apps/tiktok/products/{id}`
Delete a product.

---

## Campaigns

Base: `/campaigns`

### `GET /campaigns`
List all campaigns.

### `POST /campaigns`
Create a campaign.

```json
{
  "name": "My Campaign",
  "description": "Q3 push",
  "platform_default": "tiktok",
  "timezone": "Asia/Kuala_Lumpur"
}
```

### `GET /campaigns/{id}`
Get a campaign.

### `PUT /campaigns/{id}`
Update a campaign.

### `DELETE /campaigns/{id}`
Delete a campaign.

### `POST /campaigns/{id}/start`
Start the campaign. Enqueues all WAITING jobs.

```json
{ "simulate": false }
```

### `POST /campaigns/{id}/pause`
Pause all active queue entries.

### `POST /campaigns/{id}/resume`
Resume paused entries.

### `POST /campaigns/{id}/cancel`
Cancel all active entries.

### `GET /campaigns/{id}/jobs`
List jobs in a campaign.

### `GET /campaigns/{id}/validate`
Validate before starting.

```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Job #3 (TikTok): no video_path"]
}
```

### `GET /campaigns/{id}/estimate`
Estimate remaining time.

### `GET /campaigns/{id}/history`
Campaign audit log.

### `GET /campaigns/{id}/stats`
Statistics (success rate, avg duration, retry count).

### Campaign Jobs

`POST /campaigns/jobs` — create a job  
`GET /campaigns/jobs/{id}` — get job  
`PUT /campaigns/jobs/{id}` — update job  
`DELETE /campaigns/jobs/{id}` — delete job  
`POST /campaigns/jobs/{id}/pause` — pause  
`POST /campaigns/jobs/{id}/resume` — resume  
`POST /campaigns/jobs/{id}/cancel` — cancel  
`POST /campaigns/jobs/{id}/retry` — retry a failed job  
`POST /campaigns/jobs/{id}/simulate` — dry-run single job  

### Queue

`GET /campaigns/queue` — active queue + counts  
`GET /campaigns/queue/all` — full queue including completed  
`POST /campaigns/queue/pause` — pause entire queue  
`POST /campaigns/queue/resume` — resume queue  
`POST /campaigns/queue/reorder` — change job priority order  
`DELETE /campaigns/queue/{entry_id}` — cancel a queue entry  

### Global

`GET /campaigns/history` — global history  
`GET /campaigns/stats` — global stats  

---

## Execution

Base: `/execution`

### `GET /execution/jobs`
List recent execution jobs.

### `GET /execution/jobs/{id}`
Get a job's current state.

### `POST /execution/jobs/{id}/cancel`
Cancel a running job.

---

## Vision

Base: `/vision`

### `POST /vision/analyze`
Analyze current device screen.

```json
{ "adb_address": "...", "device_id": "..." }
```

### `GET /vision/history/{device_id}`
Recent screen analysis history.

---

## Workflows

Base: `/workflows`

### `GET /workflows`
List all workflows.

### `POST /workflows`
Create a workflow.

### `GET /workflows/{id}`
Get a workflow with all steps.

### `PUT /workflows/{id}`
Update metadata.

### `DELETE /workflows/{id}`
Delete.

### `POST /workflows/{id}/run`
Execute a workflow on a device.

### `GET /workflows/{id}/versions`
Version history.

### `POST /workflows/{id}/rollback/{version}`
Restore a previous version.

### Recorder

`POST /workflows/recorder/start` — start recording session  
`POST /workflows/recorder/{session_id}/add-step` — add a step  
`DELETE /workflows/recorder/{session_id}/steps/{index}` — remove a step  
`POST /workflows/recorder/{session_id}/stop` — stop and optionally save  

---

## WebSocket Endpoints

| Path | Purpose |
|---|---|
| `/ws/stream/{device_id}` | ADB agent → backend frame push |
| `/ws/view/{device_id}` | Browser → receives screen frames |
| `/ws/control/{device_id}` | Browser → sends touch/key commands |
| `/ws/video/{device_id}` | H264 stream to browser WebCodecs |
| `/ws/execution/{device_id}` | Live execution state JSON |
| `/ws/vision/{device_id}` | Live ScreenAnalysis JSON |
| `/ws/workflow/{channel_id}` | Workflow/recorder events |
| `/ws/campaign/{channel_id}` | Campaign + queue updates |

**Campaign WebSocket messages:**
```json
{ "event": "queue_update", "queue": [...], "counts": {...}, "paused": false }
{ "event": "campaign_update", "campaign": {...} }
```
