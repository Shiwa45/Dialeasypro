package com.dialeasypro.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log

/**
 * Keeps the microphone usable while a call is in progress.
 *
 * The problem this solves: RECORD_AUDIO is a "while in use" permission. The
 * moment the agent taps Call, the system dialer comes to the front and this
 * app is backgrounded — and a backgrounded app gets SILENCE from the mic on
 * Android 11+, and is refused outright on 12+. So the in-app fallback
 * recording produced empty or missing files on essentially every modern
 * device, silently, which is why calls appeared to record nothing.
 *
 * A foreground service with the `microphone` type is the documented way to
 * hold that access across the transition. The catch is that Android 12+ also
 * forbids STARTING a foreground service from the background — so this must be
 * started while the app is still visible, i.e. at dial time, not when the call
 * connects. DialerNotifier.dialCurrent() is that moment.
 *
 * Deliberately framework-only (no androidx): this module declares no support
 * libraries, and a notification is not worth a new dependency.
 */
class CallAudioService : Service() {

    companion object {
        private const val TAG = "CallAudioService"
        private const val CHANNEL_ID = "dialeasypro_call_audio"
        private const val NOTIFICATION_ID = 4711

        /**
         * Must be called while the app is in the foreground. Returns false if
         * Android refused the start, so the caller can record that rather than
         * assume the mic is live.
         */
        fun start(context: Context): Boolean = try {
            val intent = Intent(context, CallAudioService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            true
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException on 12+ when we are
            // already in the background. Not fatal: the OEM-recorder path does
            // not depend on this.
            Log.w(TAG, "Could not start call audio service: ${e.javaClass.simpleName}")
            false
        }

        fun stop(context: Context) {
            try {
                context.stopService(Intent(context, CallAudioService::class.java))
            } catch (e: Exception) {
                Log.w(TAG, "Could not stop call audio service: ${e.message}")
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startForeground(NOTIFICATION_ID, buildNotification())
        } catch (e: Exception) {
            Log.w(TAG, "startForeground rejected: ${e.javaClass.simpleName}")
            stopSelf()
            return START_NOT_STICKY
        }
        // Do not resurrect after the process dies: a recording that outlives
        // the call it belongs to is worse than no recording.
        return START_NOT_STICKY
    }

    private fun startForeground(id: Int, notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Android 14 requires the declared type to match the manifest, and
            // requires FOREGROUND_SERVICE_MICROPHONE to be granted.
            super.startForeground(id, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            super.startForeground(id, notification)
        }
    }

    private fun buildNotification(): Notification {
        ensureChannel()

        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pending = launch?.let { PendingIntent.getActivity(this, 0, it, flags) }

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }

        return builder
            .setContentTitle("Call recording active")
            .setContentText("DialEasypro is recording this call for your CRM.")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .also { b -> pending?.let { b.setContentIntent(it) } }
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Call recording",
            // LOW: the notification is legally required and must be visible,
            // but it should never make a sound in the middle of a sales call.
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Shown while a call is being recorded for the CRM."
            setShowBadge(false)
            enableVibration(false)
            setSound(null, null)
        }
        manager.createNotificationChannel(channel)
    }

    override fun onDestroy() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        super.onDestroy()
    }
}
