package com.dialeasypro.app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog

/**
 * Reads the phone's own record of a call that just ended.
 *
 * The app cannot time a call itself: during the call the phone's dialer is on
 * screen and Android freezes this app, and the "call started" signal fires the
 * moment dialling begins — not when the customer answers — so every outgoing
 * call looked connected. The system call log has the real talk time, and a
 * duration of 0 means nobody answered.
 */
object CallLogReader {

    /**
     * The most recent OUTGOING call to [number] (matched on its last 10
     * digits) placed at or after [sinceMillis]. Returns
     * {found, durationSec, dateMillis} or {found: false, reason}.
     */
    fun findOutgoing(context: Context, number: String, sinceMillis: Long): Map<String, Any> {
        if (context.checkSelfPermission(Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return mapOf("found" to false, "reason" to "permission")
        }
        val wanted = number.filter { it.isDigit() }.takeLast(10)
        if (wanted.isEmpty()) return mapOf("found" to false, "reason" to "number")

        val projection = arrayOf(CallLog.Calls.NUMBER, CallLog.Calls.DATE, CallLog.Calls.DURATION)
        // A little slack before the dial time: the log stamps the moment the
        // call was placed, which can precede our own timestamp slightly.
        val selection = "${CallLog.Calls.TYPE} = ? AND ${CallLog.Calls.DATE} >= ?"
        val args = arrayOf(CallLog.Calls.OUTGOING_TYPE.toString(), (sinceMillis - 15_000).toString())

        return try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI, projection, selection, args,
                "${CallLog.Calls.DATE} DESC",
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    val logged = (cursor.getString(0) ?: "").filter { it.isDigit() }.takeLast(10)
                    if (logged == wanted) {
                        return mapOf(
                            "found" to true,
                            "dateMillis" to cursor.getLong(1),
                            "durationSec" to cursor.getLong(2).toInt(),
                        )
                    }
                }
                mapOf("found" to false, "reason" to "not_yet")
            } ?: mapOf("found" to false, "reason" to "unavailable")
        } catch (e: SecurityException) {
            mapOf("found" to false, "reason" to "permission")
        } catch (e: Exception) {
            mapOf("found" to false, "reason" to "error")
        }
    }
}
