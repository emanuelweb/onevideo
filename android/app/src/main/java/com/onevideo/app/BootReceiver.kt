package com.onevideo.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * Receptor de arranque: tras reiniciar el celular, si el dispositivo está
 * emparejado, publica una notificación que con UN toque abre MainActivity con
 * [MainActivity.EXTRA_AUTO_RESUME] para dejar la cámara lista (o reanudar la
 * transmisión si estaba activa antes del reinicio).
 *
 * Android 14/15 PROHÍBE iniciar un foreground service de tipo camera/microphone
 * desde BOOT_COMPLETED (background): el patrón permitido es exactamente este —
 * notificación → toque del usuario → Activity visible → startForegroundService.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in BOOT_ACTIONS) return
        val prefs = Prefs(context)
        if (!prefs.isPaired) return
        showResumeNotification(context, prefs.wasStreaming)
    }

    companion object {
        /** BOOT_COMPLETED estándar + variantes de arranque rápido de algunos OEM. */
        private val BOOT_ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON",
            "com.htc.intent.action.QUICKBOOT_POWERON",
        )

        private const val CHANNEL_ID = "avisos"
        const val NOTIFICATION_ID = 2001

        /**
         * Publica (con NotificationManager plano, sin servicio de por medio) la
         * notificación de reanudación. La usa también StreamService cuando un
         * reinicio START_STICKY en background es vetado por el sistema.
         */
        fun showResumeNotification(context: Context, wasStreaming: Boolean) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                return // sin permiso de notificaciones no hay nada que mostrar
            }

            val manager = context.getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.notif_channel_avisos_name),
                NotificationManager.IMPORTANCE_HIGH,
            ).apply { description = context.getString(R.string.notif_channel_avisos_description) }
            manager.createNotificationChannel(channel)

            val tapIntent = PendingIntent.getActivity(
                context,
                2,
                Intent(context, MainActivity::class.java)
                    .putExtra(MainActivity.EXTRA_AUTO_RESUME, true)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

            val text = context.getString(
                if (wasStreaming) R.string.notif_resume_streaming else R.string.notif_resume_ready,
            )
            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_stream)
                .setContentTitle(context.getString(R.string.notif_reboot_title))
                .setContentText(text)
                .setContentIntent(tapIntent)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .build()
            manager.notify(NOTIFICATION_ID, notification)
        }
    }
}
