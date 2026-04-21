package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.data.models.InverterMetrics
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * 2x2 grid of live power readouts — matches iOS PowerCardsGrid.
 * LazyVerticalGrid with fixed height keeps scroll-performance good while still
 * laying out adaptively.
 */
@Composable
fun PowerCardsGrid(metrics: InverterMetrics, showEstimated: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SolarCard(metrics, modifier = Modifier.weight(1f))
            BatteryCard(metrics, modifier = Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            GridCard(metrics, showEstimated, modifier = Modifier.weight(1f))
            LoadCard(metrics, modifier = Modifier.weight(1f))
        }
    }
}

@Composable
private fun SolarCard(m: InverterMetrics, modifier: Modifier) {
    PowerCard(
        title = "Solar Production",
        value = "${m.solar.power.roundToInt()}",
        unit = "W",
        tint = Palette.Solar,
        icon = Icons.Filled.WbSunny,
        modifier = modifier,
    ) {
        Row {
            Text(text = "%.1f V".format(m.solar.voltage), color = Color.White.copy(0.85f), fontSize = 11.sp)
            Spacer(Modifier.weight(1f))
            Text(text = "%.2f A".format(m.solar.current), color = Color.White.copy(0.85f), fontSize = 11.sp)
        }
    }
}

@Composable
private fun BatteryCard(m: InverterMetrics, modifier: Modifier) {
    PowerCard(
        title = "Battery",
        value = "${m.battery.percentage.roundToInt()}",
        unit = "%",
        tint = Palette.Battery,
        icon = Icons.Filled.BatteryFull,
        modifier = modifier,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Text(m.battery.direction.label, color = Color.White.copy(0.85f), fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text("${abs(m.battery.power).roundToInt()} W", color = Color.White.copy(0.85f), fontSize = 11.sp)
            }
            Row {
                Text("%.2f V".format(m.battery.voltage), color = Palette.SubtleText, fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text("%.2f A".format(abs(m.battery.current)), color = Palette.SubtleText, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun GridCard(m: InverterMetrics, showEstimated: Boolean, modifier: Modifier) {
    PowerCard(
        title = "Grid",
        value = "${m.grid.power.roundToInt()}",
        unit = "W",
        tint = Palette.Grid,
        icon = Icons.Filled.Power,
        trailingBadge = if (showEstimated && m.grid.estimated) "EST" else null,
        modifier = modifier,
    ) {
        Row {
            Text("${m.grid.voltage.roundToInt()} V", color = Color.White.copy(0.85f), fontSize = 11.sp)
            Spacer(Modifier.weight(1f))
            Text("%.1f Hz".format(m.grid.frequency), color = Color.White.copy(0.85f), fontSize = 11.sp)
        }
    }
}

@Composable
private fun LoadCard(m: InverterMetrics, modifier: Modifier) {
    PowerCard(
        title = "Load",
        value = "${m.load.effectivePower.roundToInt()}",
        unit = "W",
        tint = Palette.Load,
        icon = Icons.Filled.Home,
        modifier = modifier,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Text("${m.load.apparentPower.roundToInt()} VA", color = Color.White.copy(0.85f), fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text("PF %.2f".format(m.load.powerFactor), color = Color.White.copy(0.85f), fontSize = 11.sp)
            }
            Row {
                Text("${m.load.voltage.roundToInt()} V", color = Palette.SubtleText, fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text("${m.load.percentage.roundToInt()}%", color = Palette.SubtleText, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun PowerCard(
    title: String,
    value: String,
    unit: String,
    tint: Color,
    icon: ImageVector,
    trailingBadge: String? = null,
    modifier: Modifier = Modifier,
    footer: @Composable () -> Unit,
) {
    Column(
        modifier = modifier
            .card()
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = tint, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Icon(icon, contentDescription = null, tint = tint.copy(alpha = 0.8f), modifier = Modifier.size(18.dp))
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(4.dp))
            Text(unit, color = Palette.SubtleText, fontSize = 13.sp)
            if (trailingBadge != null) {
                Spacer(Modifier.width(6.dp))
                Text(
                    trailingBadge,
                    color = tint.copy(alpha = 0.9f),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clip(RoundedCornerShape(999.dp))
                        .background(tint.copy(alpha = 0.15f))
                        .padding(horizontal = 5.dp, vertical = 2.dp),
                )
            }
        }
        footer()
    }
}

