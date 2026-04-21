package com.bilalahmad.invertermonitor.ui.screens.reports

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.HistoryRow
import com.bilalahmad.invertermonitor.data.viewmodels.MonthlyTotal
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.math.max

@Composable
fun MonthReport(vm: ReportsViewModel) {
    val monthDate by vm.monthDate.collectAsStateWithLifecycle()
    val monthStats by vm.monthStats.collectAsStateWithLifecycle()
    val monthHistory by vm.monthHistory.collectAsStateWithLifecycle()
    val phase by vm.monthPhase.collectAsStateWithLifecycle()
    var showPicker by remember { mutableStateOf(false) }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().card().clickable { showPicker = true }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Filled.CalendarMonth, contentDescription = null, tint = Palette.MutedText)
            Spacer(Modifier.width(10.dp))
            Text(
                SimpleDateFormat("MMMM yyyy", Locale.getDefault()).format(monthDate),
                color = Color.White, fontSize = 14.sp, modifier = Modifier.weight(1f)
            )
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = null, tint = Palette.MutedText)
        }

        PhaseIndicator(phase)

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Solar", Palette.Solar, kwhFromWh(monthStats.solarEnergyWh), "kWh", Modifier.weight(1f))
            SummaryKpi("Grid", Palette.Grid, kwhFromWh(monthStats.gridEnergyWh), "kWh", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Load", Palette.Load, kwhFromWh(monthStats.loadEnergyWh), "kWh", Modifier.weight(1f))
            SummaryKpi("Bat. +/-", Palette.Battery,
                "${kwhFromWh(monthStats.batteryChargeEnergyWh)} / ${kwhFromWh(monthStats.batteryDischargeEnergyWh)}",
                "kWh", Modifier.weight(1f))
        }

        Column(modifier = Modifier.fillMaxWidth().card().padding(14.dp)) {
            Text("Daily Breakdown", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            if (monthHistory.isEmpty()) {
                Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                    Text("No daily rows yet", color = Palette.SubtleText, fontSize = 12.sp)
                }
            } else {
                DailyBarChart(rows = monthHistory, modifier = Modifier.fillMaxWidth().height(260.dp))
            }
        }
    }

    if (showPicker) {
        MonthPickerDialog(
            current = monthDate,
            onDismiss = { showPicker = false },
            onConfirm = { vm.setMonth(it); showPicker = false }
        )
    }
}

@Composable
fun YearReport(vm: ReportsViewModel) {
    val yearValue by vm.yearValue.collectAsStateWithLifecycle()
    val yearStats by vm.yearStats.collectAsStateWithLifecycle()
    val totals by vm.monthlyTotals.collectAsStateWithLifecycle()
    val phase by vm.yearPhase.collectAsStateWithLifecycle()
    var expanded by remember { mutableStateOf(false) }
    val currentYear = Calendar.getInstance().get(Calendar.YEAR)
    val years = (currentYear downTo (currentYear - 4)).toList()

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().card().clickable { expanded = true }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Filled.CalendarMonth, contentDescription = null, tint = Palette.MutedText)
            Spacer(Modifier.width(10.dp))
            Text(yearValue.toString(), color = Color.White, fontSize = 14.sp, modifier = Modifier.weight(1f))
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = null, tint = Palette.MutedText)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            years.forEach { y ->
                DropdownMenuItem(text = { Text(y.toString()) }, onClick = { vm.setYear(y); expanded = false })
            }
        }

        PhaseIndicator(phase)

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Solar", Palette.Solar, kwhFromWh(yearStats.solarEnergyWh), "kWh", Modifier.weight(1f))
            SummaryKpi("Grid", Palette.Grid, kwhFromWh(yearStats.gridEnergyWh), "kWh", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Load", Palette.Load, kwhFromWh(yearStats.loadEnergyWh), "kWh", Modifier.weight(1f))
            SummaryKpi("Bat. +/-", Palette.Battery,
                "${kwhFromWh(yearStats.batteryChargeEnergyWh)} / ${kwhFromWh(yearStats.batteryDischargeEnergyWh)}",
                "kWh", Modifier.weight(1f))
        }

        Column(modifier = Modifier.fillMaxWidth().card().padding(14.dp)) {
            Text("Monthly Breakdown", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            if (totals.isEmpty()) {
                Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                    Text("No data for this year", color = Palette.SubtleText, fontSize = 12.sp)
                }
            } else {
                MonthlyBarChart(totals = totals, modifier = Modifier.fillMaxWidth().height(260.dp))
            }
        }
    }
}

@Composable
private fun MonthPickerDialog(current: Date, onDismiss: () -> Unit, onConfirm: (Date) -> Unit) {
    // Simple month picker — two dropdowns (year / month). iOS uses native DatePicker;
    // Compose Material 3's DatePicker shows days we don't need, so this is cleaner.
    val cal = Calendar.getInstance().apply { time = current }
    var year by remember { mutableStateOf(cal.get(Calendar.YEAR)) }
    var month by remember { mutableStateOf(cal.get(Calendar.MONTH)) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Palette.BackgroundMid,
        titleContentColor = Color.White,
        textContentColor = Palette.MutedText,
        title = { Text("Pick a month") },
        text = {
            Column {
                Text("Year", color = Palette.SubtleText, fontSize = 11.sp)
                var yExpand by remember { mutableStateOf(false) }
                TextButton(onClick = { yExpand = true }) { Text(year.toString()) }
                DropdownMenu(expanded = yExpand, onDismissRequest = { yExpand = false }) {
                    val currentYear = Calendar.getInstance().get(Calendar.YEAR)
                    (currentYear downTo currentYear - 4).forEach {
                        DropdownMenuItem(text = { Text(it.toString()) }, onClick = { year = it; yExpand = false })
                    }
                }
                Spacer(Modifier.height(8.dp))
                Text("Month", color = Palette.SubtleText, fontSize = 11.sp)
                var mExpand by remember { mutableStateOf(false) }
                val monthNames = listOf("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec")
                TextButton(onClick = { mExpand = true }) { Text(monthNames[month]) }
                DropdownMenu(expanded = mExpand, onDismissRequest = { mExpand = false }) {
                    monthNames.forEachIndexed { idx, name ->
                        DropdownMenuItem(text = { Text(name) }, onClick = { month = idx; mExpand = false })
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val c = Calendar.getInstance().apply { set(year, month, 15) }
                onConfirm(c.time)
            }) { Text("Apply") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

private fun kwhFromWh(wh: Double) = String.format(Locale.US, "%.2f", wh / 1000.0)

/** Simple stacked-per-day bar chart for the month view. 4 series × N days. */
@Composable
private fun DailyBarChart(rows: List<HistoryRow>, modifier: Modifier = Modifier) {
    val maxY = remember(rows) {
        rows.flatMap { listOf(it.solarKwh, it.gridKwh, it.loadKwh, it.batteryChargeKwh) }.maxOrNull() ?: 1.0
    }.coerceAtLeast(1.0)

    Canvas(modifier = modifier) {
        if (rows.isEmpty()) return@Canvas
        val leftPad = 40.dp.toPx()
        val bottomPad = 20.dp.toPx()
        val plotW = size.width - leftPad - 4.dp.toPx()
        val plotH = size.height - bottomPad - 4.dp.toPx()
        val groupWidth = plotW / rows.size
        val barWidth = (groupWidth - 2.dp.toPx()) / 4f

        rows.forEachIndexed { i, r ->
            val gx = leftPad + i * groupWidth + 1.dp.toPx()
            drawBar(gx,                    r.solarKwh,        maxY, plotH, barWidth, Palette.Solar)
            drawBar(gx + barWidth,          r.gridKwh,         maxY, plotH, barWidth, Palette.Grid)
            drawBar(gx + barWidth * 2,      r.loadKwh,         maxY, plotH, barWidth, Palette.Load)
            drawBar(gx + barWidth * 3,      r.batteryChargeKwh, maxY, plotH, barWidth, Palette.Battery)
        }
    }
}

@Composable
private fun MonthlyBarChart(totals: List<MonthlyTotal>, modifier: Modifier = Modifier) {
    val maxY = remember(totals) {
        totals.flatMap { listOf(it.solar, it.grid, it.load, it.battery) }.maxOrNull() ?: 1.0
    }.coerceAtLeast(1.0)

    Canvas(modifier = modifier) {
        if (totals.isEmpty()) return@Canvas
        val leftPad = 40.dp.toPx()
        val bottomPad = 20.dp.toPx()
        val plotW = size.width - leftPad - 4.dp.toPx()
        val plotH = size.height - bottomPad - 4.dp.toPx()
        val groupWidth = plotW / totals.size
        val barWidth = (groupWidth - 2.dp.toPx()) / 4f

        totals.forEachIndexed { i, t ->
            val gx = leftPad + i * groupWidth + 1.dp.toPx()
            drawBar(gx,                    t.solar,   maxY, plotH, barWidth, Palette.Solar)
            drawBar(gx + barWidth,          t.grid,    maxY, plotH, barWidth, Palette.Grid)
            drawBar(gx + barWidth * 2,      t.load,    maxY, plotH, barWidth, Palette.Load)
            drawBar(gx + barWidth * 3,      t.battery, maxY, plotH, barWidth, Palette.Battery)
        }
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawBar(
    x: Float, value: Double, maxY: Double, plotH: Float, barWidth: Float, color: Color,
) {
    val h = (max(0.0, value) / maxY).toFloat() * plotH
    if (h <= 0f) return
    drawRect(color, topLeft = Offset(x, size.height - 20.dp.toPx() - h), size = Size(barWidth, h))
}
