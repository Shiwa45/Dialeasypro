package com.dialeasypro.app

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.File

/**
 * Audio files written in a time window, found through Android's media index
 * (MediaStore) instead of a fixed list of folders.
 *
 * Call recordings land in a different folder on every brand and ROM version
 * (Recordings/Call, MIUI/sound_recorder/call_rec, Recordings/Record/Call,
 * Music/Recordings/Call Recordings, ...), and the folder list kept missing
 * new ones. MediaStore indexes every one of them, wherever it is, and can be
 * read with the ordinary audio permission — the Play Store build has no
 * "All files access" to list folders with at all.
 */
object RecordingFinder {

    /**
     * Audio files modified between [fromMillis] and [toMillis]: each
     * {path, name, folder, modifiedMillis, size, durationMs, uri}. `path` can
     * be empty when the index doesn't give one; `uri` always works with
     * [copyToFile].
     */
    fun find(context: Context, fromMillis: Long, toMillis: Long, limit: Int = 200): List<Map<String, Any>> {
        val out = ArrayList<Map<String, Any>>()
        for (collection in collections()) {
            try {
                query(context, collection, fromMillis, toMillis, limit, out)
            } catch (e: Exception) {
                // One unreadable volume (an SD card being removed) must not
                // hide the others.
            }
            if (out.size >= limit) break
        }
        return out
    }

    private fun collections(): List<Uri> {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            return listOf(MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL))
        }
        return listOf(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI)
    }

    @Suppress("DEPRECATION")
    private fun query(
        context: Context, collection: Uri, fromMillis: Long, toMillis: Long, limit: Int,
        out: MutableList<Map<String, Any>>,
    ) {
        val cols = mutableListOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.DISPLAY_NAME,
            MediaStore.Audio.Media.DATE_MODIFIED,
            MediaStore.Audio.Media.SIZE,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATA,
        )
        val hasRelative = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
        if (hasRelative) cols.add(MediaStore.Audio.Media.RELATIVE_PATH)

        // DATE_MODIFIED is in seconds.
        val selection = "${MediaStore.Audio.Media.DATE_MODIFIED} >= ? AND ${MediaStore.Audio.Media.DATE_MODIFIED} <= ?"
        val args = arrayOf((fromMillis / 1000).toString(), (toMillis / 1000 + 1).toString())

        context.contentResolver.query(
            collection, cols.toTypedArray(), selection, args,
            "${MediaStore.Audio.Media.DATE_MODIFIED} DESC",
        )?.use { c ->
            val iId = c.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val iName = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME)
            val iMod = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DATE_MODIFIED)
            val iSize = c.getColumnIndexOrThrow(MediaStore.Audio.Media.SIZE)
            val iDur = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val iData = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DATA)
            val iRel = if (hasRelative) c.getColumnIndex(MediaStore.Audio.Media.RELATIVE_PATH) else -1
            while (c.moveToNext() && out.size < limit) {
                val id = c.getLong(iId)
                val path = c.getString(iData) ?: ""
                val folder = when {
                    iRel >= 0 && !c.isNull(iRel) -> c.getString(iRel) ?: ""
                    path.isNotEmpty() -> File(path).parent ?: ""
                    else -> ""
                }
                out.add(
                    mapOf(
                        "uri" to ContentUris.withAppendedId(collection, id).toString(),
                        "path" to path,
                        "name" to (c.getString(iName) ?: File(path).name),
                        "folder" to folder,
                        "modifiedMillis" to c.getLong(iMod) * 1000,
                        "size" to c.getLong(iSize),
                        "durationMs" to (if (c.isNull(iDur)) -1L else c.getLong(iDur)),
                    )
                )
            }
        }
    }

    /**
     * Copy a MediaStore item into [dest] (app storage) and return its path,
     * or null. For files the app can see in the index but not open by path.
     */
    fun copyToFile(context: Context, uri: String, dest: File): String? = try {
        dest.parentFile?.mkdirs()
        context.contentResolver.openInputStream(Uri.parse(uri))?.use { input ->
            dest.outputStream().use { output -> input.copyTo(output) }
        }
        if (dest.exists() && dest.length() > 0) dest.absolutePath else null
    } catch (e: Exception) {
        null
    }
}
