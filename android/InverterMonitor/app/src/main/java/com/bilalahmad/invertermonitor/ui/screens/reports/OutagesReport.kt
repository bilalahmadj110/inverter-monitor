package com.bilalahmad.invertermonitor.ui.screens.reports

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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.Outage
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Locale

@Composable
fun OutagesReport(vm: ReportsViewModel) {
    val outages by vm.outages.collectAsStateWithLifecycle()
    val phase by vm.outagesPhase.collectAsStateWithLifecycle()

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().card().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = { vm.applyOutagePreset(7) },
                colors = ButtonDefaults.buttonColors(containerColor = Color.White.copy(alpha = 0.1f)),
            ) { Text("7d", color = Color.White) }
            Button(
                onClick = { vm.applyOutagePreset(30) },
                colors = ButtonDefaults.buttonColors(containerColor = Color.White.copy(alpha = 0.1f)),
            ) { Text("30d", color = Color.White) }
            Spacer(Modifier.weight(1f))
            Button(
                onClick = { vm.loadOutages() },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB)),
            ) { Text("Apply", color = Color.White) }
        }

        PhaseIndicator(phase)

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryKpi("Outages", Color(0xFFFF6B6B), outages.count.toString(), "count", Modifier.weight(1f))
            SummaryKpi("Downtime", Color(0xFFFFA726),
                String.format(Locale.US, "%.2f", outages.totalDownSeconds / 3600.0),
                "hours", Modifier.weight(1f))
        }
        SummaryKpi("Availability", Color(0xFF4ADE80),
            String.format(Locale.US, "%.2f", outages.availability * 100),
            "%", Modifier.fillMaxWidth())

        Column(modifier = Modifier.fillMaxWidth().card().padding(14.dp)) {
            Text("Outage List", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            if (outages.outages.isEmpty()) {
                Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = Color(0xFF4ADE80))
                        Spacer(Modifier.height(6.dp))
                        Text("No outages in this range", color = Palette.SubtleText, fontSize = 11.sp)
                    }
                }
            } else {
                Column {
                    outages.outages.forEach { OutageRow(it) }
                }
            }
        }
    }
}

@Composable
private fun OutageRow(outage: Outage) {
    val fmt = SimpleDateFormat("MMM d, h:mm a", Locale.getDefault())
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.weight(1f)) {
            Text(fmt.format(outage.startDate), color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Text(fmt.format(outage.endDate), color = Palette.SubtleText, fontSize = 10.sp)
        }
        Text(formatDuration(outage.durationSeconds), color = Color(0xFFFFA726), fontSize = 12.sp)
    }
}

private fun formatDuration(seconds: Int): String {
    if (seconds < 60) return "${seconds}s"
    val mins = seconds / 60
    val secs = seconds % 60
    if (mins < 60) return if (secs > 0) "${mins}m ${secs}s" else "${mins}m"
    val hours = mins / 60
    val remMin = mins % 60
    return if (remMin > 0) "${hours}h ${remMin}m" else "${hours}h"
}
