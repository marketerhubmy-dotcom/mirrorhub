package com.mirrorhub.agent.control

import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import com.mirrorhub.agent.services.AgentAccessibilityService

class KeyboardController {

    fun inputText(text: String) {
        val service = AgentAccessibilityService.instance ?: return
        val root = service.rootInActiveWindow ?: return
        val focused = findFocused(root) ?: return

        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        focused.recycle()
        root.recycle()
    }

    fun sendKey(keycode: String) {
        val service = AgentAccessibilityService.instance ?: return
        when (keycode) {
            "KEYCODE_ENTER" -> pressEnter(service)
            "KEYCODE_DEL" -> pressDelete(service)
            else -> Unit
        }
    }

    private fun pressEnter(service: AgentAccessibilityService) {
        val root = service.rootInActiveWindow ?: return
        val focused = findFocused(root)
        focused?.performAction(AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT_GRANULARITY)
        focused?.recycle()
        root.recycle()
    }

    private fun pressDelete(service: AgentAccessibilityService) {
        val root = service.rootInActiveWindow ?: return
        val focused = findFocused(root) ?: return
        val current = focused.text?.toString() ?: ""
        if (current.isNotEmpty()) {
            val args = Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    current.dropLast(1),
                )
            }
            focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        }
        focused.recycle()
        root.recycle()
    }

    private fun findFocused(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isFocused && node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findFocused(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }
}
