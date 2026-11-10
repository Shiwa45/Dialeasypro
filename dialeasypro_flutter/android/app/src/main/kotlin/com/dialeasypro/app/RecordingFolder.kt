package com.dialeasypro.app

import android.content.Context
import android.content.Intent
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.DocumentsContract

/**
 * The recordings folder the agent chose ("Select recordings folder").
 *
 * Every call recorder saves somewhere different, and on phones whose dialer
 * keeps its recordings private the agent installs a recorder app (Cube ACR,
 * a recording dialer) instead. Either way the agent points the app at the
 * folder once, through Android's own folder picker, and the app keeps read
 * access to it — no "All files access" needed, so this also works in the
 * Play Store build.
 */
object RecordingFolder {

    const val REQUEST_CODE = 7341

    fun pickIntent(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
        addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
        )
    }

    /** Keep access across restarts. Returns {uri, label} or null. */
    fun persist(context: Context, uri: Uri): Map<String, Any>? = try {
        context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        mapOf("uri" to uri.toString(), "label" to label(uri))
    } catch (e: Exception) {
        null
    }

    /** "Recordings/Call" for a tree on primary storage, the raw id otherwise. */
    fun label(uri: Uri): String = try {
        val id = DocumentsContract.getTreeDocumentId(uri)
        val colon = id.indexOf(':')
        val volume = if (colon >= 0) id.substring(0, colon) else ""
        val path = if (colon >= 0) id.substring(colon + 1) else id
        when {
            volume.equals("primary", true) -> if (path.isEmpty()) "Internal storage" else path
            else -> "$volume/$path"
        }
    } catch (e: Exception) {
        uri.toString()
    }

    fun hasAccess(context: Context, uri: String): Boolean = try {
        context.contentResolver.persistedUriPermissions.any { it.uri.toString() == uri && it.isReadPermission }
    } catch (e: Exception) {
        false
    }

    private val audioExt = setOf("m4a", "mp3", "amr", "wav", "aac", "3gp", "ogg", "mp4", "opus", "awb")

    /**
     * Audio files in the chosen folder and its subfolders (a few levels:
     * several recorders bucket by date or contact) modified between
     * [fromMillis] and [toMillis]: each {uri, name, folder, modifiedMillis,
     * size}. Newest first; at most [limit].
     */
    fun list(context: Context, treeUri: String, fromMillis: Long, toMillis: Long, limit: Int = 300): List<Map<String, Any>> {
        val out = ArrayList<Map<String, Any>>()
        val tree = try { Uri.parse(treeUri) } catch (e: Exception) { return out }
        val rootId = try { DocumentsContract.getTreeDocumentId(tree) } catch (e: Exception) { return out }
        walk(context, tree, rootId, "", 0, fromMillis, toMillis, limit, out)
        out.sortByDescending { it["modifiedMillis"] as Long }
        return out
    }

    private fun walk(
        context: Context, tree: Uri, docId: String, folder: String, depth: Int,
        fromMillis: Long, toMillis: Long, limit: Int, out: MutableList<Map<String, Any>>,
    ) {
        if (depth > 3 || out.size >= limit) return
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val cols = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
            DocumentsContract.Document.COLUMN_SIZE,
        )
        val subfolders = ArrayList<Pair<String, String>>()
        try {
            context.contentResolver.query(children, cols, null, null, null)?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getString(0) ?: continue
                    val name = c.getString(1) ?: ""
                    val mime = c.getString(2) ?: ""
                    if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                        subfolders.add(id to name)
                        continue
                    }
                    val modified = if (c.isNull(3)) 0L else c.getLong(3)
                    if (modified < fromMillis || modified > toMillis) continue
                    val ext = name.substringAfterLast('.', "").lowercase()
                    if (!mime.startsWith("audio/") && ext !in audioExt) continue
                    out.add(
                        mapOf(
                            "uri" to DocumentsContract.buildDocumentUriUsingTree(tree, id).toString(),
                            "name" to name,
                            "folder" to folder,
                            "modifiedMillis" to modified,
                            "size" to (if (c.isNull(4)) 0L else c.getLong(4)),
                        )
                    )
                    if (out.size >= limit) return
                }
            }
        } catch (e: Exception) {
            return
        }
        for ((id, name) in subfolders) {
            walk(context, tree, id, if (folder.isEmpty()) name else "$folder/$name", depth + 1,
                fromMillis, toMillis, limit, out)
        }
    }

    /** Length of a content:// audio file in ms, or null. */
    fun durationMs(context: Context, uri: String): Long? {
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(context, Uri.parse(uri))
            r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
        } catch (e: Exception) {
            null
        } finally {
            try { r.release() } catch (e: Exception) {}
        }
    }
}
