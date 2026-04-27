package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun SystemInfoGrid(
    temperature: Double,
    busVoltage: Double,
    modeLabel: String,
    connectionLabel: String,
    lastUpdate: Date?,
    todayTemperatureMax: Double,
    readingDurationMs: Double?,
    errorCount: Int,
    totalReadings: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            InfoTile(
                title = "Inverter Temp",
                value = if (temperature <= 0) "—" else "${temperature.roundToInt()}",
                unit = "°C",
                footnote = "Today peak ${todayTemperatureMax.roundToInt()}°C",
                modifier = Modifier.weight(1f),
            )
            InfoTile(
                title = "DC Bus Voltage",
                value = if (busVoltage <= 0) "—" else "${busVoltage.roundToInt()}",
                unit = "V",
                footnote = "Mode: $modeLabel",
                modifier = Modifier.weight(1f),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            InfoTile(
                title = "Connection",
                value = connectionLabel,
                unit = null,
                footnote = lastUpdate?.let { "Last update ${SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(it)}" } ?: "Waiting…",
                modifier = Modifier.weight(1f),
            )
            InfoTile(
                title = "Reading Cycle",
                value = readingDurationMs?.takeIf { it > 0 }?.roundToInt()?.toString() ?: "—",
                unit = "ms",
                footnote = "Errors $errorCount / $totalReadings",
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun InfoTile(title: String, value: String, unit: String?, footnote: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .card()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(title, color = Palette.SubtleText, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            if (unit != null) {
                Spacer(Modifier.width(4.dp))
                Text(unit, color = Palette.SubtleText, fontSize = 11.sp)
            }
        }
        Text(footnote, color = Palette.SubtleText, fontSize = 10.sp)
    }
}
