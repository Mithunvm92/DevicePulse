package com.devicepulse.kiosk

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    private lateinit var brokerInput: EditText
    private lateinit var topicInput: EditText
    private lateinit var deviceInput: EditText
    private lateinit var intervalInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 36, 32, 24)
            gravity = Gravity.CENTER_VERTICAL
        }

        layout.addView(TextView(this).apply {
            text = "DevicePulse Kiosk — MVP"
            textSize = 23f
        })
        layout.addView(TextView(this).apply {
            text = "Configure a test MQTT broker. Use TLS and credentials for real deployments."
            textSize = 14f
            setPadding(0, 8, 0, 18)
        })

        brokerInput = field("Broker URI (e.g. tcp://192.168.1.10:1883)", "tcp://")
        topicInput = field("MQTT topic", "devicepulse/kiosk/heartbeat")
        deviceInput = field("Device ID", android.os.Build.MODEL.replace(" ", "-"))
        intervalInput = field("Heartbeat interval seconds", "60")

        layout.addView(brokerInput)
        layout.addView(topicInput)
        layout.addView(deviceInput)
        layout.addView(intervalInput)

        layout.addView(Button(this).apply {
            text = "Start monitoring"
            setOnClickListener {
                val interval = intervalInput.text.toString().toLongOrNull()?.coerceIn(15, 3600) ?: 60L
                val intent = Intent(this@MainActivity, MonitoringService::class.java).apply {
                    putExtra("brokerUri", brokerInput.text.toString().trim())
                    putExtra("topic", topicInput.text.toString().trim())
                    putExtra("deviceId", deviceInput.text.toString().trim())
                    putExtra("intervalSeconds", interval)
                }
                try {
                    startForegroundService(intent)
                    Toast.makeText(this@MainActivity, "Monitoring service requested", Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Could not start: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        })

        layout.addView(Button(this).apply {
            text = "Stop monitoring"
            setOnClickListener {
                stopService(Intent(this@MainActivity, MonitoringService::class.java))
                Toast.makeText(this@MainActivity, "Monitoring service stopped", Toast.LENGTH_SHORT).show()
            }
        })

        setContentView(layout)
    }

    private fun field(hintText: String, initial: String): EditText =
        EditText(this).apply {
            hint = hintText
            setSingleLine(true)
            setText(initial)
            textSize = 14f
        }
}
