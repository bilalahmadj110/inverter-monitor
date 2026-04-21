package com.bilalahmad.invertermonitor.ui.screens.reports

import android.content.Intent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.DayReadingPoint
import com.bilalahmad.invertermonitor.data.services.InverterService
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.components.ToastBanner
import com.bilalahmad.invertermonitor.ui.components.ToastStyle
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun DayReport(vm: ReportsViewModel) {
    val dayDate by vm.dayDate.collectAsStateWithLifecycle()
    val daySummary by vm.daySummary.collectAsStateWithLifecycle()
    val dayReadings by vm.dayReadings.collectAsStateWithLifecycle()
    val phase by vm.dayPhase.collectAsStateWithLifecycle()
    val exportError by vm.exportError.collectAsStateWithLifecycle()

    var showExportDialog by remember { mutableStateOf(false) }
    var selectedIndex by remember { mutableStateOf<Int?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        // Nav controls
        Row(
            modifier = Modifier.fillMaxWidth().card().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            IconButton(onClick = { vm.shiftDay(-1) }) {
                Icon(Icons.Filled.ChevronLeft, contentDescription = "Previous day", tint = Color.White)
            }
            Text(
                SimpleDateFormat("EEE, MMM d", Locale.getDefault()).format(dayDate),
                color = Color.White,
                modifier = Modifier.weight(1f),
                fontSize = 14.sp,
            )
            IconButton(onClick = { vm.shiftDay(1) }) {
                Icon(Icons.Filled.ChevronRight, contentDescription = "Next day", tint = Color.White)
            }
            Button(
                onClick = { vm.jumpToToday() },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB)),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
            ) { Text("Today", fontSize = 12.sp) }
            IconButton(onClick = { showExportDialog = true }) {
                Icon(Icons.Filled.Share, contentDescription = "Export", tint = Color.White)
            }
        }

        PhaseIndicator(phase)

        // KPI summary
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Solar", Palette.Solar, kwh(daySummary.solarKwh),
                "Peak ${daySummary.solarPeakW.roundToInt()}W", Modifier.weight(1f))
            SummaryKpi("Grid Import", Palette.Grid, kwh(daySummary.gridKwh),
                "Peak ${daySummary.gridPeakW.roundToInt()}W", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Load", Palette.Load, kwh(daySummary.loadKwh),
                "Peak ${daySummary.loadPeakW.roundToInt()}W", Modifier.weight(1f))
            SummaryKpi("Bat. +/-", Palette.Battery,
                "${kwh(daySummary.batteryChargeKwh)} / ${kwh(daySummary.batteryDischargeKwh)}",
                "kWh", Modifier.weight(1f))
        }
        SummaryKpi("Self-Sufficiency", Color(0xFF4ADE80),
            "${(daySummary.selfSufficiency * 100).roundToInt()}%",
            "Solar share ${(daySummary.solarFraction * 100).roundToInt()}%",
            Modifier.fillMaxWidth())

        // Power timeline chart
        Column(
            modifier = Modifier.fillMaxWidth().card().padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Power Timeline", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            if (dayReadings.points.isEmpty()) {
                Box(modifier = Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                    Text("No readings for this day", color = Palette.SubtleText, fontSize = 12.sp)
                }
            } else {
                DayChart(
                    points = dayReadings.points,
                    selectedIndex = selectedIndex,
                    onSelect = { selectedIndex = it },
                    modifier = Modifier.fillMaxWidth().height(300.dp),
                )
            }
        }

        exportError?.let { ToastBanner(it, ToastStyle.ERROR) }
    }

    // Export sheet
    if (showExportDialog) {
        AlertDialog(
            onDismissRequest = { showExportDialog = false },
            title = { Text("Export day") },
            text = {
                Column {
                    listOf(
                        Triple("Raw 3s · CSV", InverterService.ExportFormat.CSV, null),
                        Triple("Raw 3s · JSON", InverterService.ExportFormat.JSON, null),
                        Triple("1-min · CSV", InverterService.ExportFormat.CSV, 60),
                        Triple("1-min · JSON", InverterService.ExportFormat.JSON, 60),
                        Triple("5-min · CSV", InverterService.ExportFormat.CSV, 300),
                        Triple("5-min · JSON", InverterService.ExportFormat.JSON, 300),
                    ).forEach { (label, format, bucket) ->
                        TextButton(
                            onClick = {
                                showExportDialog = false
                                scope.launch { doExport(vm, context, format, bucket) }
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text(label) }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showExportDialog = false }) { Text("Cancel") } },
            containerColor = Palette.BackgroundMid,
            titleContentColor = Color.White,
            textContentColor = Palette.MutedText,
        )
    }
}

private suspend fun doExport(
    vm: ReportsViewModel,
    context: android.content.Context,
    format: InverterService.ExportFormat,
    bucket: Int?,
) {
    val result = vm.exportDay(format, bucket) ?: return
    val file = File(context.cacheDir, result.filename)
    file.writeBytes(result.data)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = result.mime
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Share export"))
}

private fun kwh(v: Double) = String.format(Locale.US, "%.2f", v)

@Composable
private fun DayChart(
    points: List<DayReadingPoint>,
    selectedIndex: Int?,
    onSelect: (Int?) -> Unit,
    modifier: Modifier = Modifier,
) {
    val allYs = remember(points) {
        points.flatMap { listOf(it.solarPower, it.gridPower, it.loadPower, it.batteryPower) }
    }
    val yMin = allYs.minOrNull() ?: 0.0
    val yMax = allYs.maxOrNull() ?: 1.0
    val yRange = (yMax - yMin).let { if (it < 1.0) 1.0 else it }

    Box(modifier = modifier) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(points) {
                    detectTapGestures { offset ->
                        val ratio = ((offset.x - 50f) / (size.width - 58f)).coerceIn(0f, 1f)
                        onSelect(((points.size - 1) * ratio).roundToInt().coerceIn(0, points.size - 1))
                    }
                }
        ) {
            val leftPad = 50.dp.toPx()
            val plotW = size.width - leftPad - 8.dp.toPx()
            val topPad = 8.dp.toPx()
            val plotH = size.height - topPad - 24.dp.toPx()

            fun xFor(i: Int): Float {
                val r = if (points.size <= 1) 0f else i / (points.size - 1f)
                return leftPad + r * plotW
            }
            fun yFor(v: Double): Float = topPad + plotH - ((v - yMin) / yRange).toFloat() * plotH

            // Horizontal gridlines
            for (t in 0..4) {
                val y = topPad + (t / 4f) * plotH
                drawLine(Palette.CardBorder, Offset(leftPad, y), Offset(leftPad + plotW, y),
                    0.5.dp.toPx())
            }

            fun drawSeries(color: Color, dashed: Boolean, selector: (DayReadingPoint) -> Double) {
                val path = Path().apply {
                    moveTo(xFor(0), yFor(selector(points[0])))
                    for (i in 1 until points.size) lineTo(xFor(i), yFor(selector(points[i])))
                }
                drawPath(path, color,
                    style = Stroke(
                        width = 2.dp.toPx(),
                        pathEffect = if (dashed) PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx())) else null,
                    ),
                )
            }
            drawSeries(Palette.Solar, false) { it.solarPower }
            drawSeries(Palette.Grid, false) { it.gridPower }
            drawSeries(Palette.Load, false) { it.loadPower }
            drawSeries(Palette.Battery, true) { it.batteryPower }

            if (selectedIndex != null && selectedIndex in points.indices) {
                val x = xFor(selectedIndex)
                drawLine(Color.White.copy(alpha = 0.35f),
                    Offset(x, topPad), Offset(x, topPad + plotH),
                    1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 3.dp.toPx())))
                val p = points[selectedIndex]
                drawCircle(Palette.Solar, 4.dp.toPx(), Offset(x, yFor(p.solarPower)))
                drawCircle(Palette.Grid, 4.dp.toPx(), Offset(x, yFor(p.gridPower)))
                drawCircle(Palette.Load, 4.dp.toPx(), Offset(x, yFor(p.loadPower)))
                drawCircle(Palette.Battery, 4.dp.toPx(), Offset(x, yFor(p.batteryPower)))
            }
        }

        if (selectedIndex != null && selectedIndex in points.indices) {
            val p = points[selectedIndex]
            Column(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 4.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(Color.Black.copy(alpha = 0.85f))
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                val fmt = SimpleDateFormat("HH:mm", Locale.getDefault())
                Text(fmt.format(p.date), color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Text("Solar ${p.solarPower.roundToInt()} W", color = Palette.Solar, fontSize = 10.sp)
                Text("Grid ${p.gridPower.roundToInt()} W", color = Palette.Grid, fontSize = 10.sp)
                Text("Load ${p.loadPower.roundToInt()} W", color = Palette.Load, fontSize = 10.sp)
                Text("Battery ${p.batteryPower.roundToInt()} W", color = Palette.Battery, fontSize = 10.sp)
                Text("SoC ${p.batteryPercentage.roundToInt()}%", color = Color.White, fontSize = 10.sp)
            }
        }
    }
}
