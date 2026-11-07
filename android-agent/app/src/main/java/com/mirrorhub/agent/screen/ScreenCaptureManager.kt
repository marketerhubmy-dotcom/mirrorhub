package com.mirrorhub.agent.screen

import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.os.Handler
import android.os.HandlerThread
import java.io.ByteArrayOutputStream

class ScreenCaptureManager(
    private val projection: MediaProjection,
    private val width: Int,
    private val height: Int,
    private val dpi: Int,
    private val onFrame: (ByteArray) -> Unit,
) {
    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null
    private val handlerThread = HandlerThread("ScreenCapture").also { it.start() }
    private val handler = Handler(handlerThread.looper)

    // throttle to ~30 fps
    private var lastFrameMs = 0L
    private val frameIntervalMs = 1000L / 30

    fun start() {
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)

        imageReader!!.setOnImageAvailableListener({ reader ->
            val now = System.currentTimeMillis()
            if (now - lastFrameMs < frameIntervalMs) {
                reader.acquireLatestImage()?.close()
                return@setOnImageAvailableListener
            }
            lastFrameMs = now

            val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                val plane = image.planes[0]
                val buffer = plane.buffer
                val pixelStride = plane.pixelStride
                val rowStride = plane.rowStride
                val rowPadding = rowStride - pixelStride * width

                val bitmap = Bitmap.createBitmap(
                    width + rowPadding / pixelStride,
                    height,
                    Bitmap.Config.ARGB_8888,
                )
                bitmap.copyPixelsFromBuffer(buffer)

                val cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height)
                bitmap.recycle()

                val out = ByteArrayOutputStream()
                cropped.compress(Bitmap.CompressFormat.JPEG, 70, out)
                cropped.recycle()

                onFrame(out.toByteArray())
            } finally {
                image.close()
            }
        }, handler)

        virtualDisplay = projection.createVirtualDisplay(
            "MirrorHubCapture",
            width, height, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface,
            null, null,
        )
    }

    fun stop() {
        virtualDisplay?.release()
        imageReader?.close()
        handlerThread.quitSafely()
        projection.stop()
    }
}
