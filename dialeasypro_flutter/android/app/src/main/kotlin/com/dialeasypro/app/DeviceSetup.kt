package com.dialeasypro.app

import android.app.Activity
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.telecom.TelecomManager
import android.util.Log

/**
 * Brand-specific plumbing for first-run setup.
 *
 * Everything here is a best effort by design. Android has no standard intent
 * for "open the dialer's call-recording setting", and the OEM screens that do
 * exist are undocumented activities that get renamed between ROM versions. So
 * each helper walks a cascade of candidates and reports whether anything
 * opened; the wizard always shows written steps as the reliable fallback, and
 * a failure here must never look like a crash to the agent.
 */
object DeviceSetup {

    private const val TAG = "DeviceSetup"

    fun deviceInfo(context: Context): Map<String, Any> = mapOf(
        "manufacturer" to (Build.MANUFACTURER ?: ""),
        "brand" to (Build.BRAND ?: ""),
        "model" to (Build.MODEL ?: ""),
        "sdkInt" to Build.VERSION.SDK_INT,
        "dialerPackage" to (defaultDialer(context) ?: ""),
    )

    /** The package actually handling calls — not a guess from the brand name. */
    private fun defaultDialer(context: Context): String? = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val tm = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager
            tm?.defaultDialerPackage
        } else null
    } catch (e: Exception) {
        null
    }

    // ---- Call recording settings ---------------------------------

    /**
     * Try to land the agent on the screen where call recording is switched on.
     *
     * Cascade: known settings activity for the installed dialer → just launch
     * the dialer → the dialer's app-info page. Returns the step reached so the
     * wizard can adjust its wording rather than claiming more than it did.
     */
    fun openCallRecordingSettings(activity: Activity): String {
        val dialer = defaultDialer(activity)

        // Undocumented, version-specific, and wrapped in try/catch for exactly
        // that reason. Ordered most- to least- specific.
        val candidates = listOf(
            // Google Phone (Motorola, Nokia, stock Android, many others)
            "com.google.android.dialer" to
                "com.android.dialer.callrecord.impl.CallRecordingSettingsActivity",
            "com.google.android.dialer" to
                "com.android.dialer.settings.DialerSettingsActivity",
            // Samsung
            "com.samsung.android.dialer" to
                "com.samsung.android.dialer.settings.DialerSettingsActivity",
            // Xiaomi / Redmi / POCO
            "com.android.contacts" to
                "com.android.contacts.callrecord.CallRecordSettingsActivity",
            "com.miui.contacts" to
                "com.android.contacts.activities.CallRecordSettingActivity",
            // Vivo / iQOO
            "com.android.incallui" to
                "com.android.incallui.recorder.RecorderSettingActivity",
            // Oppo / Realme / OnePlus (ColorOS)
            "com.coloros.soundrecorder" to
                "com.coloros.soundrecorder.CallRecordSettingActivity",
        )

        for ((pkg, cls) in candidates) {
            // Only try activities belonging to the dialer this phone actually
            // uses, or we send the agent into an unrelated app.
            if (dialer != null && pkg != dialer && !pkg.startsWith(dialer.substringBeforeLast('.'))) {
                continue
            }
            if (launchComponent(activity, pkg, cls)) return "settings"
        }

        if (dialer != null && launchPackage(activity, dialer)) return "dialer"
        if (dialer != null && openAppInfo(activity, dialer)) return "app_info"
        return "none"
    }

    // ---- Battery / background execution ---------------------------

    fun isIgnoringBatteryOptimizations(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        return try {
            val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
            pm.isIgnoringBatteryOptimizations(context.packageName)
        } catch (e: Exception) {
            true // Unknown: do not nag about something we cannot verify.
        }
    }

    /**
     * Ask to be exempted from battery optimisation, so aggressive OEM power
     * management does not kill the app between calls and stall the recording
     * sweep. Falls back to the general list, which needs no permission.
     */
    fun requestIgnoreBatteryOptimizations(activity: Activity): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return false
        try {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                .setData(Uri.parse("package:${activity.packageName}"))
            activity.startActivity(intent)
            return true
        } catch (e: Exception) {
            Log.w(TAG, "Direct battery exemption unavailable: ${e.javaClass.simpleName}")
        }
        return try {
            activity.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Autostart / background-start whitelists. Xiaomi, Vivo, Oppo, Realme and
     * Transsion (Infinix/Tecno) kill backgrounded apps unless the user allows
     * them here, and there is no API to check the state — only to open the
     * screen. Samsung and Motorola are handled by battery optimisation alone.
     */
    fun openAutoStartSettings(activity: Activity): Boolean {
        val components = listOf(
            // Xiaomi / Redmi / POCO
            "com.miui.securitycenter" to "com.miui.permcenter.autostart.AutoStartManagementActivity",
            // Oppo / Realme
            "com.coloros.safecenter" to "com.coloros.safecenter.permission.startup.StartupAppListActivity",
            "com.coloros.safecenter" to "com.coloros.safecenter.startupapp.StartupAppListActivity",
            "com.oppo.safe" to "com.oppo.safe.permission.startup.StartupAppListActivity",
            // Vivo / iQOO
            "com.vivo.permissionmanager" to "com.vivo.permissionmanager.activity.BgStartUpManagerActivity",
            "com.iqoo.secure" to "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity",
            // Transsion — Infinix / Tecno / itel
            "com.transsion.phonemaster" to "com.cyin.himgr.autostart.AutoStartActivity",
            // Huawei / Honor
            "com.huawei.systemmanager" to "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity",
            // Samsung device care
            "com.samsung.android.lool" to "com.samsung.android.sm.battery.ui.BatteryActivity",
        )
        for ((pkg, cls) in components) {
            if (launchComponent(activity, pkg, cls)) return true
        }
        return false
    }

    // ---- Low-level helpers ---------------------------------------

    private fun launchComponent(activity: Activity, pkg: String, cls: String): Boolean = try {
        val intent = Intent().setComponent(ComponentName(pkg, cls))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        // resolveActivity first: starting a missing component throws, and on
        // some ROMs the throw is a SecurityException rather than a miss.
        if (activity.packageManager.resolveActivity(intent, 0) != null) {
            activity.startActivity(intent)
            true
        } else false
    } catch (e: Exception) {
        false
    }

    private fun launchPackage(activity: Activity, pkg: String): Boolean = try {
        val intent = activity.packageManager.getLaunchIntentForPackage(pkg)
        if (intent != null) {
            activity.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            true
        } else false
    } catch (e: Exception) {
        false
    }

    private fun openAppInfo(activity: Activity, pkg: String): Boolean = try {
        activity.startActivity(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse("package:$pkg"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        true
    } catch (e: Exception) {
        false
    }
}
