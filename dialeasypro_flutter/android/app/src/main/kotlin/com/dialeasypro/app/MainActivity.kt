package com.dialeasypro.app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private companion object {
        const val CHANNEL = "dialeasypro/call_audio"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // Lets the Dart side hold the microphone across the moment the system
        // dialer takes over the screen. See CallAudioService for why this
        // cannot be done from Dart alone.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
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
    }
}
