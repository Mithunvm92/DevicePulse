package com.devicepulse.kiosk

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import java.net.InetAddress
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MonitoringService : Service() {
    private val executor = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var running = false
    private var client: MqttClient? = null
    private var brokerUri = ""
    private var topic = "devicepulse/kiosk/heartbeat"
    private var deviceId = "android-kiosk"
    private var intervalSeconds = 60L

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(101, notification("Monitoring service starting"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        brokerUri = intent?.getStringExtra("brokerUri") ?: ""
        topic = intent?.getStringExtra("topic") ?: topic
        deviceId = intent?.getStringExtra("deviceId") ?: deviceId
        intervalSeconds = intent?.getLongExtra("intervalSeconds", 60L) ?: 60L
        intervalSeconds = intervalSeconds.coerceIn(15, 3600)

        if (!running) {
            running = true
            executor.scheduleWithFixedDelay({ publishHeartbeat() }, 0, intervalSeconds, TimeUnit.SECONDS)
        }
        return START_STICKY
    }

    private fun publishHeartbeat() {
        try {
            if (brokerUri.isBlank() || !brokerUri.startsWith("tcp://") && !brokerUri.startsWith("ssl://")) {
                updateNotification("Configure a valid tcp:// or ssl:// MQTT broker URI")
                return
            }
            val mqtt = getConnectedClient()
            val now = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).format(Date())
            val payload = JSONObject()
                .put("deviceId", deviceId)
                .put("timestamp", now)
                .put("uptimeSeconds", SystemClock.elapsedRealtime() / 1000)
                .put("androidVersion", Build.VERSION.RELEASE)
                .put("sdkInt", Build.VERSION.SDK_INT)
                .put("manufacturer", Build.MANUFACTURER)
                .put("model", Build.MODEL)
                .put("networkConnected", isNetworkConnected())
                .put("batteryPercent", batteryPercent())
                .put("appVersion", "0.1.0")
                .toString()
            mqtt.publish(topic, MqttMessage(payload.toByteArray(Charsets.UTF_8)).apply { qos = 1; isRetained = false })
            updateNotification("Last heartbeat sent at ${SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())}")
        } catch (e: Exception) {
            updateNotification("MQTT publish failed: ${e.javaClass.simpleName}")
            try { client?.disconnectForcibly() } catch (_: Exception) {}
            client = null
        }
    }

    private fun getConnectedClient(): MqttClient {
        val existing = client
        if (existing != null && existing.isConnected) return existing
        val newClient = MqttClient(brokerUri, "devicepulse-${UUID.randomUUID()}", MemoryPersistence())
        val options = MqttConnectOptions().apply {
            isAutomaticReconnect = true
            isCleanSession = true
            connectionTimeout = 8
            keepAliveInterval = 30
        }
        newClient.connect(options)
        client = newClient
        return newClient
    }

    private fun isNetworkConnected(): Boolean {
        return try {
            val cm = getSystemService(CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
            val network = cm.activeNetwork
            network != null && cm.getNetworkCapabilities(network) != null
        } catch (_: Exception) { false }
    }

    private fun batteryPercent(): Int {
        val bm = getSystemService(BATTERY_SERVICE) as android.os.BatteryManager
        return bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    private fun notification(message: String): Notification {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, "devicepulse")
                .setContentTitle("DevicePulse Kiosk")
                .setContentText(message)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("DevicePulse Kiosk")
                .setContentText(message)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .build()
        }
    }

    private fun updateNotification(message: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(101, notification(message))
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel("devicepulse", "DevicePulse Monitoring", NotificationManager.IMPORTANCE_LOW)
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
    }

    override fun onDestroy() {
        running = false
        executor.shutdownNow()
        try { client?.disconnect() } catch (_: Exception) {}
        try { client?.close() } catch (_: Exception) {}
        client = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
