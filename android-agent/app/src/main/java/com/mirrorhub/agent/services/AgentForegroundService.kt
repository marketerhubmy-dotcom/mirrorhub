package com.mirrorhub.agent.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.mirrorhub.agent.R
import com.mirrorhub.agent.control.KeyboardController
import com.mirrorhub.agent.control.TouchController
import com.mirrorhub.agent.screen.ScreenCaptureManager
import com.mirrorhub.agent.websocket.AgentWebSocketClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID

class AgentForegroundService : Service() {

    companion object {
        const val EXTRA_SERVER_URL = "server_url"
        const val EXTRA_PROJECTION_CODE = "projection_code"
        const val EXTRA_PROJECTION_DATA = "projection_data"

        private const val CHANNEL_ID = "mirrorhub_agent"
        private const val NOTIF_ID = 1
        private const val PREFS = "mirrorhub_prefs"
        private const val KEY_DEVICE_ID = "device_id"
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var captureManager: ScreenCaptureManager? = null
    private var wsClient: AgentWebSocketClient? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val serverUrl = intent?.getStringExtra(EXTRA_SERVER_URL) ?: return START_NOT_STICKY
        val projCode = intent.getIntExtra(EXTRA_PROJECTION_CODE, -1)
        val projData = intent.getParcelableExtra<Intent>(EXTRA_PROJECTION_DATA)
            ?: return START_NOT_STICKY

        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification())

        val deviceId = getOrCreateDeviceId()
        val metrics = getScreenMetrics()

        val projectionManager =
            getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val projection = projectionManager.getMediaProjection(projCode, projData)

        val touchController = TouchController(metrics.widthPixels, metrics.heightPixels)
        val keyboardController = KeyboardController()

        wsClient = AgentWebSocketClient(
            serverUrl = serverUrl,
            deviceId = deviceId,
            touchController = touchController,
            keyboardController = keyboardController,
            onConnected = {
                captureManager = ScreenCaptureManager(
                    projection = projection,
                    width = metrics.widthPixels,
                    height = metrics.heightPixels,
                    dpi = metrics.densityDpi,
                    onFrame = { jpegBytes -> wsClient?.sendFrame(jpegBytes) },
                ).also { it.start() }
            },
            onDisconnected = {
                // retry after 3s
                scope.launch {
                    delay(3_000)
                    wsClient?.connect()
                }
            },
        )

        scope.launch {
            registerDevice(serverUrl, deviceId)
            wsClient?.connect()
            heartbeatLoop(serverUrl, deviceId)
        }

        return START_STICKY
    }

    override fun onDestroy() {
        captureManager?.stop()
        wsClient?.disconnect()
        scope.cancel()
        super.onDestroy()
    }

    private suspend fun registerDevice(serverUrl: String, deviceId: String) {
        try {
            val body = JSONObject().apply {
                put("device_id", deviceId)
                put("device_name", Build.MODEL)
                put("battery", 100)
                put("wifi", true)
            }.toString().toRequestBody("application/json".toMediaType())

            val request = Request.Builder()
                .url("http://$serverUrl/api/v1/devices/register")
                .post(body)
                .build()

            OkHttpClient().newCall(request).execute().close()
        } catch (_: Exception) {}
    }

    private suspend fun heartbeatLoop(serverUrl: String, deviceId: String) {
        val http = OkHttpClient()
        while (true) {
            delay(15_000)
            try {
                val body = JSONObject().apply {
                    put("device_id", deviceId)
                    put("battery", 100)
                    put("wifi", true)
                }.toString().toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("http://$serverUrl/api/v1/devices/heartbeat")
                    .post(body)
                    .build()

                http.newCall(request).execute().close()
            } catch (_: Exception) {}
        }
    }

    private fun getOrCreateDeviceId(): String {
        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(KEY_DEVICE_ID, it).apply()
        }
    }

    private fun getScreenMetrics(): DisplayMetrics {
        val metrics = DisplayMetrics()
        (getSystemService(Context.WINDOW_SERVICE) as WindowManager)
            .defaultDisplay.getRealMetrics(metrics)
        return metrics
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        )
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .createNotificationChannel(channel)
    }

    private fun buildNotification() = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle(getString(R.string.app_name))
        .setContentText(getString(R.string.notification_text))
        .setSmallIcon(android.R.drawable.ic_menu_camera)
        .build()
}
