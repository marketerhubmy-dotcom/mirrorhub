package com.mirrorhub.agent.control

import android.accessibilityservice.GestureDescription
import android.graphics.Path
import com.mirrorhub.agent.services.AgentAccessibilityService

class TouchController(
    private val screenWidth: Int,
    private val screenHeight: Int,
) {
    private fun px(relX: Double) = (relX * screenWidth).toFloat()
    private fun py(relY: Double) = (relY * screenHeight).toFloat()

    private fun dispatch(gesture: GestureDescription) {
        AgentAccessibilityService.instance?.dispatchGesture(gesture, null, null)
    }

    fun tap(relX: Double, relY: Double) {
        val path = Path().apply { moveTo(px(relX), py(relY)) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        dispatch(gesture)
    }

    fun longPress(relX: Double, relY: Double) {
        val path = Path().apply { moveTo(px(relX), py(relY)) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 600))
            .build()
        dispatch(gesture)
    }

    fun swipe(relX1: Double, relY1: Double, relX2: Double, relY2: Double) {
        val path = Path().apply {
            moveTo(px(relX1), py(relY1))
            lineTo(px(relX2), py(relY2))
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        dispatch(gesture)
    }
}
