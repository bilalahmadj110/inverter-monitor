package com.bilalahmad.invertermonitor.ui.screens.reports

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.RawReading
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlin.math.roundToInt

@Composable
fun RawReadings(vm: ReportsViewModel) {
    val rawReadings by vm.rawReadings.collectAsStateWithLifecycle()
    val rawPage by vm.rawPage.collectAsStateWithLifecycle()
    val rawPageSize by vm.rawPageSize.collectAsStateWithLifecycle()
    val phase by vm.rawPhase.collectAsStateWithLifecycle()
    var selected by remember { mutableStateOf<RawReading?>(null) }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().card().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Page size", color = Palette.SubtleText, fontSize = 11.sp)
            Spacer(Modifier.width(10.dp))
            SingleChoiceSegmentedButtonRow(modifier = Modifier.weight(1f)) {
                listOf(10, 25, 50, 100).forEachIndexed { idx, size ->
                    SegmentedButton(
                        selected = rawPageSize == size,
                        onClick = { vm.setPageSize(size) },
                        shape = SegmentedButtonDefaults.itemShape(idx, 4),
                        colors = SegmentedButtonDefaults.colors(
                            activeContainerColor = Palette.Solar.copy(alpha = 0.3f),
                            activeContentColor = Color.White,
                            inactiveContainerColor = Color.Transparent,
                            inactiveContentColor = Palette.MutedText,
                        ),
                        label = { Text(size.toString(), fontSize = 11.sp) },
                    )
                }
            }
        }

        PhaseIndicator(phase)

        if (rawReadings.data.isNotEmpty()) {
            Column(modifier = Modifier.fillMaxWidth().card()) {
                // Header row
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("Time", color = Palette.SubtleText, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    Text("Solar", color = Palette.SubtleText, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
                    Text("Grid", color = Palette.SubtleText, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
                    Text("Load", color = Palette.SubtleText, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
                    Text("Bat %", color = Palette.SubtleText, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
                }
                HorizontalDivider(color = Palette.Divider)
                rawReadings.data.forEach { row ->
                    RawRow(row) { selected = row }
                }
            }

            // Paginator
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                IconButton(onClick = { vm.goToPage(1) }, enabled = rawPage > 1) {
                    Icon(Icons.Filled.KeyboardDoubleArrowLeft, null, tint = Color.White)
                }
                IconButton(onClick = { vm.goToPage(rawPage - 1) }, enabled = rawPage > 1) {
                    Icon(Icons.Filled.ChevronLeft, null, tint = Color.White)
                }
                Spacer(Modifier.weight(1f))
                Text("Page $rawPage of ${rawReadings.totalPages.coerceAtLeast(1)}",
                     color = Color.White, fontSize = 12.sp)
                Text("(${rawReadings.totalCount} rows)", color = Palette.SubtleText, fontSize = 10.sp,
                     modifier = Modifier.padding(start = 6.dp))
                Spacer(Modifier.weight(1f))
                IconButton(onClick = { vm.goToPage(rawPage + 1) }, enabled = rawPage < rawReadings.totalPages) {
                    Icon(Icons.Filled.ChevronRight, null, tint = Color.White)
                }
                IconButton(onClick = { vm.goToPage(rawReadings.totalPages) }, enabled = rawPage < rawReadings.totalPages) {
                    Icon(Icons.Filled.KeyboardDoubleArrowRight, null, tint = Color.White)
                }
            }
        }
    }

    selected?.let { reading ->
        RawReadingDetailSheet(reading = reading, onDismiss = { selected = null })
    }
}

@Composable
private fun RawRow(row: RawReading, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(row.timestampFormatted, color = Color.White, fontSize = 11.sp, maxLines = 1, modifier = Modifier.weight(1f))
        Text("${row.solarPower.roundToInt()}", color = solarColor(row.solarPower),
             fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
        Text("${row.gridPower.roundToInt()}", color = Palette.Grid,
             fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
        Text("${row.loadPower.roundToInt()}", color = Palette.Load,
             fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
        Text("${row.batteryPercentage.roundToInt()}%", color = batteryColor(row.batteryPercentage),
             fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(50.dp))
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = Palette.SubtleText)
    }
    HorizontalDivider(color = Palette.Divider)
}

private fun solarColor(w: Double): Color = when {
    w > 100 -> Palette.Solar
    w > 0 -> Palette.Solar.copy(alpha = 0.6f)
    else -> Palette.SubtleText
}
private fun batteryColor(pct: Double): Color = when {
    pct >= 50 -> Palette.Battery
    pct >= 20 -> Color(0xFFFFA726)
    else -> Color(0xFFFF6B6B)
}
