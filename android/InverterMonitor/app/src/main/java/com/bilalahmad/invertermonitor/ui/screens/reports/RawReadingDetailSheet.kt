package com.bilalahmad.invertermonitor.ui.screens.reports

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.bilalahmad.invertermonitor.data.models.RawReading
import com.bilalahmad.invertermonitor.ui.components.InfoRow
import com.bilalahmad.invertermonitor.ui.components.SheetCard
import com.bilalahmad.invertermonitor.ui.components.SheetScaffold
import com.bilalahmad.invertermonitor.ui.components.SheetSectionHeader
import com.bilalahmad.invertermonitor.ui.components.StatTile
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlin.math.roundToInt

@Composable
fun RawReadingDetailSheet(reading: RawReading, onDismiss: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Palette.BackgroundTop,
    ) {
        SheetScaffold(
            icon = Icons.Filled.Timeline,
            iconTint = Palette.InverterAmber,
            title = reading.timestampFormatted,
            subtitle = "Inverter reading",
            onDismiss = onDismiss,
        ) {
            // Power section — 2x2 grid, tinted values to match the live charts.
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SheetSectionHeader("Power", accent = Palette.InverterAmber)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile("Solar", "${reading.solarPower.roundToInt()}", "W", Palette.Solar, Modifier.weight(1f))
                    StatTile("Grid", "${reading.gridPower.roundToInt()}", "W", Palette.Grid, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile("Load", "${reading.loadPower.roundToInt()}", "W", Palette.Load, Modifier.weight(1f))
                    StatTile("Battery", "${reading.batteryPower.roundToInt()}", "W", Palette.Battery, Modifier.weight(1f))
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SheetSectionHeader("Battery", accent = Palette.Battery)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile(
                        "State of Charge",
                        "${reading.batteryPercentage.roundToInt()}", "%",
                        batteryColor(reading.batteryPercentage),
                        Modifier.weight(1f),
                    )
                    StatTile(
                        "Direction",
                        directionLabel(reading.batteryPower),
                        accent = Color.White,
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SheetSectionHeader("Environment", accent = Palette.Grid)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile("Grid Voltage", "${reading.gridVoltage.roundToInt()}", "V", Color.White, Modifier.weight(1f))
                    StatTile("Inverter Temp", "${reading.temperature.roundToInt()}", "°C", Color.White, Modifier.weight(1f))
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SheetSectionHeader("Raw", accent = Palette.SubtleText)
                SheetCard {
                    InfoRow("Timestamp", reading.timestampFormatted)
                    InfoRow("Epoch seconds", "${reading.timestamp.toLong()}")
                    InfoRow("Cycle duration", String.format(java.util.Locale.US, "%.1f ms", reading.durationMs))
                }
            }
        }
    }
}

private fun directionLabel(power: Double): String = when {
    power > 5 -> "Charging"
    power < -5 -> "Discharging"
    else -> "Idle"
}

private fun batteryColor(pct: Double): Color = when {
    pct >= 50 -> Palette.Battery
    pct >= 20 -> Color(0xFFFFA726)
    else -> Color(0xFFFF6B6B)
}
