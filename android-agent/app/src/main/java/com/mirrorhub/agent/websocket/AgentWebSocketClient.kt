package com.mirrorhub.agent.websocket

import com.mirrorhub.agent.control.KeyboardController
import com.mirrorhub.agent.control.TouchController
import com.mirrorhub.agent.services.AgentAccessibilityService
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class AgentWebSocketClient(
    private val serverUrl: String,
    private val deviceId: String,
    private val touchController: TouchController,
    private val keyboardController: KeyboardController,
    private val onConnected: () -> Unit,
    private val onDisconnected: () -> Unit,
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    private var socket: WebSocket? = null

    fun connect() {
        val url = "ws://$serverUrl/ws/stream/$deviceId"
        val request = Request.Builder().url(url).build()

        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleControl(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                onDisconnected()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                onDisconnected()
            }
        })
    }

    fun sendFrame(jpegBytes: ByteArray) {
        socket?.send(jpegBytes.toByteString())
    }

    fun disconnect() {
        socket?.close(1000, "Agent stopped")
        client.dispatcher.executorService.shutdown()
    }

    private fun handleControl(json: String) {
        try {
            val obj = JSONObject(json)
            when (obj.getString("type")) {
                "tap" -> touchController.tap(obj.getDouble("x"), obj.getDouble("y"))
                "long_press" -> touchController.longPress(obj.getDouble("x"), obj.getDouble("y"))
                "swipe" -> touchController.swipe(
                    obj.getDouble("x1"), obj.getDouble("y1"),
                    obj.getDouble("x2"), obj.getDouble("y2"),
                )
                "text" -> keyboardController.inputText(obj.getString("value"))
                "key" -> keyboardController.sendKey(obj.getString("code"))
                "nav" -> handleNav(obj.getString("action"))
            }
        } catch (_: Exception) {}
    }

    private fun handleNav(action: String) {
        val service = AgentAccessibilityService.instance ?: return
        when (action) {
            "home" -> service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME)
            "back" -> service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            "recents" -> service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_RECENTS)
        }
    }
}
