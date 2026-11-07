package com.mirrorhub.agent

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import androidx.appcompat.app.AppCompatActivity
import com.mirrorhub.agent.databinding.ActivityMainBinding
import com.mirrorhub.agent.services.AgentForegroundService

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val projectionManager by lazy {
        getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    }
    private var pendingServerUrl: String = ""

    companion object {
        private const val PREFS = "mirrorhub_prefs"
        private const val KEY_URL = "server_url"
        private const val REQ_PROJECTION = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        binding.etServerUrl.setText(prefs.getString(KEY_URL, ""))

        binding.btnStart.setOnClickListener {
            val url = binding.etServerUrl.text.toString().trim()
            if (url.isEmpty()) {
                binding.tvStatus.text = "Status: Enter server URL first"
                return@setOnClickListener
            }
            prefs.edit().putString(KEY_URL, url).apply()
            pendingServerUrl = url
            requestProjection()
        }

        binding.btnStop.setOnClickListener {
            stopAgent()
        }

        checkAccessibilityService()
    }

    override fun onResume() {
        super.onResume()
        checkAccessibilityService()
    }

    private fun requestProjection() {
        startActivityForResult(
            projectionManager.createScreenCaptureIntent(),
            REQ_PROJECTION,
        )
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_PROJECTION && resultCode == Activity.RESULT_OK && data != null) {
            startAgent(pendingServerUrl, resultCode, data)
        } else {
            binding.tvStatus.text = "Status: Permission denied"
        }
    }

    private fun startAgent(serverUrl: String, projectionCode: Int, projectionData: Intent) {
        val intent = Intent(this, AgentForegroundService::class.java).apply {
            putExtra(AgentForegroundService.EXTRA_SERVER_URL, serverUrl)
            putExtra(AgentForegroundService.EXTRA_PROJECTION_CODE, projectionCode)
            putExtra(AgentForegroundService.EXTRA_PROJECTION_DATA, projectionData)
        }
        startForegroundService(intent)
        binding.tvStatus.text = "Status: Running"
        binding.btnStart.isEnabled = false
        binding.btnStop.isEnabled = true
    }

    private fun stopAgent() {
        stopService(Intent(this, AgentForegroundService::class.java))
        binding.tvStatus.text = "Status: Stopped"
        binding.btnStart.isEnabled = true
        binding.btnStop.isEnabled = false
    }

    private fun checkAccessibilityService() {
        val am = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val enabled = am.installedAccessibilityServiceList.any {
            it.resolveInfo.serviceInfo.packageName == packageName
        }
        if (!enabled) {
            binding.tvAccessibility.text =
                "Accessibility not enabled — go to Settings > Accessibility > MirrorHub Control"
            binding.tvAccessibility.setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        } else {
            binding.tvAccessibility.text = ""
        }
    }
}
