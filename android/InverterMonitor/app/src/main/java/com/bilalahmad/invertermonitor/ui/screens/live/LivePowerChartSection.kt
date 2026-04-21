package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.data.models.RecentReadingPoint
import com.bilalahmad.invertermonitor.data.models.RecentReadings
import com.bilalahmad.invertermonitor.data.viewmodels.LiveRange
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Live 4-series line chart drawn with Canvas. A Vico dependency isn't worth the
 * API-churn overhead for this many marks — a plain Canvas implementation is ~150
 * lines, predictable, and handles the crosshair tooltip with one gesture.
 */
@Composable
fun LivePowerChartSection(
    readings: RecentReadings,
    range: LiveRange,
    onRangeChange: (LiveRange) -> Unit,
    isLoading: Boolean,
) {
    var selectedIndex by remember { mutableStateOf<Int?>(null) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .card()
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Live Power", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                 modifier = Modifier.weight(1f))
            RangePicker(range = range, onRangeChange = onRangeChange)
        }

        if (readings.points.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().height(240.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(if (isLoading) "Loading…" else "No data yet", color = Palette.SubtleText, fontSize = 12.sp)
            }
        } else {
            MultiLineChart(
                points = readings.points,
                selectedIndex = selectedIndex,
                onSelect = { selectedIndex = it },
                modifier = Modifier.fillMaxWidth().height(260.dp),
            )
        }

        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Legend(Palette.Solar, "Solar")
            Legend(Palette.Grid, "Grid")
            Legend(Palette.Load, "Load")
            Legend(Palette.Battery, "Battery", dashed = true)
        }
    }
}

@Composable
private fun MultiLineChart(
    points: List<RecentReadingPoint>,
    selectedIndex: Int?,
    onSelect: (Int?) -> Unit,
    modifier: Modifier = Modifier,
) {
    // Precompute the visible y-range across all four series to scale the plot.
    val allYs = remember(points) {
        points.flatMap { listOf(it.solarAvg, it.gridAvg, it.loadAvg, it.batteryAvg) }
    }
    val yMin = remember(allYs) { allYs.minOrNull() ?: 0.0 }
    val yMax = remember(allYs) { allYs.maxOrNull() ?: 1.0 }
    val yRange = (yMax - yMin).let { if (it < 1.0) 1.0 else it }

    val tooltip = selectedIndex?.let { points.getOrNull(it) }

    Box(modifier = modifier) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(points) {
                    detectTapGestures { offset ->
                        val idx = nearestIndex(offset.x, size.width.toFloat(), points.size)
                        onSelect(idx)
                    }
                }
                .pointerInput(points) {
                    detectDragGestures(onDragEnd = { /* keep selection visible */ }) { change, _ ->
                        change.consume()
                        val idx = nearestIndex(change.position.x, size.width.toFloat(), points.size)
                        onSelect(idx)
                    }
                }
        ) {
            val w = size.width
            val h = size.height
            val leftPad = 50.dp.toPx()
            val rightPad = 8.dp.toPx()
            val topPad = 8.dp.toPx()
            val bottomPad = 24.dp.toPx()
            val plotW = w - leftPad - rightPad
            val plotH = h - topPad - bottomPad

            fun xForIndex(i: Int): Float {
                val ratio = if (points.size <= 1) 0f else i / (points.size - 1f)
                return leftPad + ratio * plotW
            }
            fun yForValue(v: Double): Float {
                val ratio = ((v - yMin) / yRange).toFloat()
                return topPad + plotH - ratio * plotH
            }

            // Grid + axes
            val axisColor = Palette.CardBorder
            for (tick in 0..4) {
                val y = topPad + (tick / 4f) * plotH
                drawLine(
                    color = axisColor,
                    start = Offset(leftPad, y),
                    end = Offset(leftPad + plotW, y),
                    strokeWidth = 0.5.dp.toPx(),
                )
            }

            // Four series
            drawLineSeries(points, ::xForIndex, ::yForValue, Palette.Solar) { it.solarAvg }
            drawLineSeries(points, ::xForIndex, ::yForValue, Palette.Grid) { it.gridAvg }
            drawLineSeries(points, ::xForIndex, ::yForValue, Palette.Load) { it.loadAvg }
            drawLineSeries(points, ::xForIndex, ::yForValue, Palette.Battery, dashed = true) { it.batteryAvg }

            // Crosshair
            if (selectedIndex != null && selectedIndex in points.indices) {
                val x = xForIndex(selectedIndex)
                drawLine(
                    color = Color.White.copy(alpha = 0.35f),
                    start = Offset(x, topPad),
                    end = Offset(x, topPad + plotH),
                    strokeWidth = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 3.dp.toPx())),
                )
                val p = points[selectedIndex]
                drawCircle(Palette.Solar,   radius = 4.dp.toPx(), center = Offset(x, yForValue(p.solarAvg)))
                drawCircle(Palette.Grid,    radius = 4.dp.toPx(), center = Offset(x, yForValue(p.gridAvg)))
                drawCircle(Palette.Load,    radius = 4.dp.toPx(), center = Offset(x, yForValue(p.loadAvg)))
                drawCircle(Palette.Battery, radius = 4.dp.toPx(), center = Offset(x, yForValue(p.batteryAvg)))
            }
        }

        // Floating tooltip rendered as real Compose text (sharper than Canvas text).
        if (tooltip != null) {
            CrosshairTooltip(point = tooltip, modifier = Modifier.align(Alignment.TopCenter).padding(top = 4.dp))
        }
    }
}

private fun DrawScope.drawLineSeries(
    points: List<RecentReadingPoint>,
    xForIndex: (Int) -> Float,
    yForValue: (Double) -> Float,
    color: Color,
    dashed: Boolean = false,
    selector: (RecentReadingPoint) -> Double,
) {
    if (points.size < 2) return
    val path = Path().apply {
        moveTo(xForIndex(0), yForValue(selector(points[0])))
        // `this` inside apply is the Path being built; can't reference `path` yet.
        for (i in 1 until points.size) lineTo(xForIndex(i), yForValue(selector(points[i])))
    }
    drawPath(
        path = path,
        color = color,
        style = Stroke(
            width = 2.dp.toPx(),
            pathEffect = if (dashed) PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx())) else null,
        ),
    )
}

private fun nearestIndex(x: Float, width: Float, count: Int): Int? {
    if (count == 0) return null
    // Plot x starts at leftPad (50dp). Approximate — treat tap x as 0..width,
    // map to nearest point index. Good enough for visual alignment.
    val ratio = ((x - 50f) / (width - 58f)).coerceIn(0f, 1f)
    return (ratio * (count - 1)).roundToInt().coerceIn(0, count - 1)
}

@Composable
private fun CrosshairTooltip(point: RecentReadingPoint, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(Color.Black.copy(alpha = 0.85f))
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        val fmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
        Text(fmt.format(Date((point.timestamp * 1000.0).toLong())),
             color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        LegendRow(Palette.Solar, "Solar", point.solarAvg)
        LegendRow(Palette.Grid, "Grid", point.gridAvg)
        LegendRow(Palette.Load, "Load", point.loadAvg)
        LegendRow(Palette.Battery, "Battery", point.batteryAvg)
    }
}

@Composable
private fun LegendRow(color: Color, label: String, value: Double) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            modifier = Modifier
                .size(width = 10.dp, height = 3.dp)
                .clip(RoundedCornerShape(1.5.dp))
                .background(color)
        )
        Text(label, color = Color.White.copy(0.75f), fontSize = 10.sp)
        Spacer(Modifier.width(8.dp))
        Text("${value.roundToInt()} W", color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun Legend(color: Color, label: String, dashed: Boolean = false) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            modifier = Modifier
                .size(width = 16.dp, height = 3.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(color.copy(alpha = if (dashed) 0.6f else 1f))
        )
        Text(label, color = Palette.MutedText, fontSize = 10.sp)
    }
}

@Composable
private fun RangePicker(range: LiveRange, onRangeChange: (LiveRange) -> Unit) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color.White.copy(alpha = 0.06f)),
    ) {
        LiveRange.entries.forEach { option ->
            val active = option == range
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(if (active) Color(0xFF2563EB) else Color.Transparent)
                    .clickable { onRangeChange(option) }
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    option.label,
                    color = if (active) Color.White else Palette.MutedText,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}
