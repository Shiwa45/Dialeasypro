package com.dialeasypro.app

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private companion object {
        const val AUDIO_CHANNEL = "dialeasypro/call_audio"
        const val SETUP_CHANNEL = "dialeasypro/setup"
        const val CALL_LOG_CHANNEL = "dialeasypro/call_log"
    }

    /** The Dart call waiting for the folder picker to return. */
    private var pendingFolderPick: MethodChannel.Result? = null

    @Deprecated("FlutterActivity still routes results here")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == RecordingFolder.REQUEST_CODE) {
            val result = pendingFolderPick
            pendingFolderPick = null
            val uri = if (resultCode == RESULT_OK) data?.data else null
            result?.success(uri?.let { RecordingFolder.persist(applicationContext, it) })
            return
        }
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // Lets the Dart side hold the microphone across the moment the system
        // dialer takes over the screen. See CallAudioService for why this
        // cannot be done from Dart alone.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, AUDIO_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    // Returns whether Android actually allowed the start, so
                    // Dart can report "recording unavailable" instead of
                    // producing a silent file.
                    "start" -> result.success(CallAudioService.start(applicationContext))
                    "stop" -> {
                        CallAudioService.stop(applicationContext)
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            }

        // The real duration of a call that just ended — see CallLogReader.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CALL_LOG_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "findOutgoing" -> {
                        val number = call.argument<String>("number") ?: ""
                        val since = call.argument<Number>("sinceMillis")?.toLong() ?: 0L
                        result.success(CallLogReader.findOutgoing(applicationContext, number, since))
                    }
                    // The recordings folder the agent picks — see RecordingFolder.
                    "pickRecordingFolder" -> {
                        pendingFolderPick?.success(null)
                        pendingFolderPick = result
                        try {
                            @Suppress("DEPRECATION")
                            startActivityForResult(RecordingFolder.pickIntent(), RecordingFolder.REQUEST_CODE)
                        } catch (e: Exception) {
                            pendingFolderPick = null
                            result.success(null)
                        }
                    }
                    "hasFolderAccess" -> result.success(
                        RecordingFolder.hasAccess(applicationContext, call.argument<String>("uri") ?: "")
                    )
                    "listFolderAudio" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        val from = call.argument<Number>("fromMillis")?.toLong() ?: 0L
                        val to = call.argument<Number>("toMillis")?.toLong() ?: System.currentTimeMillis()
                        Thread {
                            val res = RecordingFolder.list(applicationContext, uri, from, to)
                            runOnUiThread { result.success(res) }
                        }.start()
                    }
                    "uriDurationMs" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        Thread {
                            val ms = RecordingFolder.durationMs(applicationContext, uri)
                            runOnUiThread { result.success(ms) }
                        }.start()
                    }
                    "hasCallLogAccess" -> result.success(
                        applicationContext.checkSelfPermission(android.Manifest.permission.READ_CALL_LOG)
                            == android.content.pm.PackageManager.PERMISSION_GRANTED
                    )
                    // Phone call tracking: every call since a moment.
                    "listSince" -> {
                        val since = call.argument<Number>("sinceMillis")?.toLong() ?: 0L
                        val limit = call.argument<Number>("limit")?.toInt() ?: 200
                        Thread {
                            val res = CallLogReader.listSince(applicationContext, since, limit)
                            runOnUiThread { result.success(res) }
                        }.start()
                    }
                    // Audio files written in a time window, from the media
                    // index — see RecordingFinder.
                    "findAudio" -> {
                        val from = call.argument<Number>("fromMillis")?.toLong() ?: 0L
                        val to = call.argument<Number>("toMillis")?.toLong() ?: System.currentTimeMillis()
                        Thread {
                            val res = RecordingFinder.find(applicationContext, from, to)
                            runOnUiThread { result.success(res) }
                        }.start()
                    }
                    "copyAudio" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        val dest = call.argument<String>("dest") ?: ""
                        Thread {
                            val res = if (uri.isEmpty() || dest.isEmpty()) null
                                else RecordingFinder.copyToFile(applicationContext, uri, java.io.File(dest))
                            runOnUiThread { result.success(res) }
                        }.start()
                    }
                    // Length of an audio file in ms (null if unreadable). Run
                    // off the main thread: reading a header can touch storage.
                    "audioDurationMs" -> {
                        val path = call.argument<String>("path") ?: ""
                        Thread {
                            val ms = AudioProbe.durationMs(path)
                            runOnUiThread { result.success(ms) }
                        }.start()
                    }
                    else -> result.notImplemented()
                }
            }

        // First-run setup: brand detection and the OEM settings screens the
        // agent has to visit. Every call reports what it managed to do rather
        // than throwing, because none of these screens are guaranteed to exist.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SETUP_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "deviceInfo" ->
                        result.success(DeviceSetup.deviceInfo(applicationContext))
                    "openCallRecordingSettings" ->
                        result.success(DeviceSetup.openCallRecordingSettings(this))
                    "isIgnoringBatteryOptimizations" ->
                        result.success(DeviceSetup.isIgnoringBatteryOptimizations(applicationContext))
                    "requestIgnoreBatteryOptimizations" ->
                        result.success(DeviceSetup.requestIgnoreBatteryOptimizations(this))
                    "openDefaultDialerSettings" ->
                        result.success(DeviceSetup.openDefaultDialerSettings(this))
                    "openAutoStartSettings" ->
                        result.success(DeviceSetup.openAutoStartSettings(this))
                    else -> result.notImplemented()
                }
            }
    }
}
