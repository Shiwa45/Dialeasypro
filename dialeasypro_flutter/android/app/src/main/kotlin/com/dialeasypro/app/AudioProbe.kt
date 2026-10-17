package com.dialeasypro.app

import android.media.MediaMetadataRetriever

/**
 * The length of an audio file, read from its own header.
 *
 * Matching a call to a recording on the phone used names and times only, so
 * a recording of a different call (or a voice memo) written at about the
 * right moment could be picked; and the app's microphone fallback produced
 * 0.2-second files that were uploaded as the call's recording. Knowing how
 * long each file really is rules both out.
 */
object AudioProbe {

    /** Milliseconds, or null when the file can't be read. */
    fun durationMs(path: String): Long? {
        if (path.isEmpty()) return null
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(path)
            retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
        } catch (e: Exception) {
            null
        } finally {
            try {
                retriever.release()
            } catch (e: Exception) {
                // Nothing to do: the probe already has its answer.
            }
        }
    }
}
