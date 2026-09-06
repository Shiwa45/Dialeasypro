package com.dialeasypro.app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private companion object {
        const val AUDIO_CHANNEL = "dialeasypro/call_audio"
        const val SETUP_CHANNEL = "dialeasypro/setup"
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
                    "openAutoStartSettings" ->
                        result.success(DeviceSetup.openAutoStartSettings(this))
                    else -> result.notImplemented()
                }
            }
    }
}
