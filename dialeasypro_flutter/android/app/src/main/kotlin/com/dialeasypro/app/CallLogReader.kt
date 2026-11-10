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

        val projection = arrayOf(
            CallLog.Calls.NUMBER, CallLog.Calls.DATE, CallLog.Calls.DURATION, CallLog.Calls.CACHED_NAME,
        )
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
                            // The contact name the dialer showed: recorders
                            // name the file after it.
                            "cachedName" to (cursor.getString(3) ?: ""),
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

    /**
     * Every call in the phone's call log placed at or after [sinceMillis],
     * oldest first, at most [limit]. For phone call tracking: each entry is
     * {id, number, type, dateMillis, durationSec, cachedName} where type is
     * incoming | outgoing | missed | rejected | blocked. Voicemail and calls
     * answered on another device are left out.
     *
     * Returns {ok: false, reason} when the call log can't be read.
     */
    fun listSince(context: Context, sinceMillis: Long, limit: Int): Map<String, Any> {
        if (context.checkSelfPermission(Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return mapOf("ok" to false, "reason" to "permission")
        }
        val projection = arrayOf(
            CallLog.Calls._ID, CallLog.Calls.NUMBER, CallLog.Calls.TYPE,
            CallLog.Calls.DATE, CallLog.Calls.DURATION, CallLog.Calls.CACHED_NAME,
        )
        val selection = "${CallLog.Calls.DATE} >= ?"
        val args = arrayOf(sinceMillis.toString())
        val calls = ArrayList<Map<String, Any>>()
        return try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI, projection, selection, args,
                "${CallLog.Calls.DATE} ASC",
            )?.use { cursor ->
                while (cursor.moveToNext() && calls.size < limit) {
                    val type = typeName(cursor.getInt(2)) ?: continue
                    calls.add(
                        mapOf(
                            "id" to cursor.getLong(0).toString(),
                            "number" to (cursor.getString(1) ?: ""),
                            "type" to type,
                            "dateMillis" to cursor.getLong(3),
                            "durationSec" to cursor.getLong(4).toInt(),
                            "cachedName" to (cursor.getString(5) ?: ""),
                        )
                    )
                }
                mapOf("ok" to true, "calls" to calls)
            } ?: mapOf("ok" to false, "reason" to "unavailable")
        } catch (e: SecurityException) {
            mapOf("ok" to false, "reason" to "permission")
        } catch (e: Exception) {
            mapOf("ok" to false, "reason" to "error")
        }
    }

    private fun typeName(type: Int): String? = when (type) {
        CallLog.Calls.INCOMING_TYPE -> "incoming"
        CallLog.Calls.OUTGOING_TYPE -> "outgoing"
        CallLog.Calls.MISSED_TYPE -> "missed"
        CallLog.Calls.REJECTED_TYPE -> "rejected"
        CallLog.Calls.BLOCKED_TYPE -> "blocked"
        else -> null // voicemail, answered externally, unknown OEM types
    }
}
