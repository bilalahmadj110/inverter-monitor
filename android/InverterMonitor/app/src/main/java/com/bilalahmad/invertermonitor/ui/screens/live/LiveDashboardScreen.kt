package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.ChargeStage
import com.bilalahmad.invertermonitor.data.models.InverterMode
import com.bilalahmad.invertermonitor.data.models.InverterWarning
import com.bilalahmad.invertermonitor.data.models.SystemInfo
import com.bilalahmad.invertermonitor.data.models.WarningSeverity
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.ui.components.StatusPill
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlinx.coroutines.launch

@Composable
fun LiveDashboardScreen(vm: LiveDashboardViewModel) {
    val status by vm.status.collectAsStateWithLifecycle()
    val summary by vm.summary.collectAsStateWithLifecycle()
    val monthStats by vm.monthStats.collectAsStateWithLifecycle()
    val yearStats by vm.yearStats.collectAsStateWithLifecycle()
    val connection by vm.connection.collectAsStateWithLifecycle()
    val recentReadings by vm.recentReadings.collectAsStateWithLifecycle()
    val liveRange by vm.liveRange.collectAsStateWithLifecycle()
    val dismissedWarnings by vm.dismissedWarnings.collectAsStateWithLifecycle()
    val isRefreshingExtras by vm.isRefreshingExtras.collectAsStateWithLifecycle()
    val lastUpdate by vm.lastUpdate.collectAsStateWithLifecycle()
    val readingStats by vm.readingStats.collectAsStateWithLifecycle()

    var selectedComponent by remember { mutableStateOf<FlowComponent?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Palette.BackgroundGradient)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp)
            .padding(top = 24.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        // Header row
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Icon(Icons.Filled.WbSunny, contentDescription = null, tint = Palette.Solar)
                    Column {
                        Text("Solar Energy System", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White)
                        Text("Real-time status", fontSize = 11.sp, color = Palette.SubtleText)
                    }
                }
            }
            IconButton(
                onClick = { vm.requestRefreshExtras() },
                enabled = !isRefreshingExtras,
            ) {
                val angle by androidx.compose.animation.core.animateFloatAsState(
                    targetValue = if (isRefreshingExtras) 360f else 0f,
                    animationSpec = if (isRefreshingExtras) {
                        androidx.compose.animation.core.infiniteRepeatable(
                            androidx.compose.animation.core.tween(durationMillis = 900, easing = androidx.compose.animation.core.LinearEasing),
                        )
                    } else {
                        androidx.compose.animation.core.tween(250)
                    },
                    label = "refresh-spin",
                )
                Icon(
                    Icons.Filled.Refresh,
                    contentDescription = "Refresh mode and warnings",
                    tint = Color.White,
                    modifier = Modifier.rotate(angle),
                )
            }
        }

        // Pill row
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModePillRow(system = status.system)
        }

        // Warnings banner (dismissible)
        AnimatedVisibility(visible = !dismissedWarnings && status.system.warnings.isNotEmpty()) {
            WarningsBanner(status.system.warnings) { vm.setDismissedWarnings(true) }
        }

        // Flow diagram
        FlowDiagram(status = status) { selectedComponent = it }

        // Power cards
        PowerCardsGrid(status.metrics, showEstimated = status.metrics.grid.inUse)

        // Today/Month/Year summary
        TodaySummarySection(summary = summary, monthStats = monthStats, yearStats = yearStats)

        // System info
        SystemInfoGrid(
            temperature = status.system.temperature,
            busVoltage = status.system.busVoltage,
            modeLabel = status.system.modeLabel.ifEmpty { status.system.mode.defaultLabel },
            connectionLabel = connection.label,
            lastUpdate = lastUpdate,
            todayTemperatureMax = summary.temperatureMax,
            readingDurationMs = status.timing?.durationMs,
            errorCount = readingStats?.errorCount ?: 0,
            totalReadings = readingStats?.totalReadings ?: 0,
        )

        // Live chart
        LivePowerChartSection(
            readings = recentReadings,
            range = liveRange,
            onRangeChange = vm::setLiveRange,
            isLoading = false,
        )
    }

    // Component detail sheet
    selectedComponent?.let { component ->
        ComponentDetailSheet(
            vm = vm,
            component = component,
            onDismiss = { selectedComponent = null },
        )
    }
}

@Composable
private fun ModePillRow(system: SystemInfo) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        val (bg, fg, dot) = modeColors(system.mode)
        StatusPill(
            label = system.modeLabel.ifEmpty { system.mode.defaultLabel },
            dotColor = dot,
            tint = fg,
            backgroundTint = bg,
            dashed = system.modeSource == "derived",
        )
        if (system.chargeStage != ChargeStage.IDLE) {
            StatusPill(
                label = system.chargeStage.label,
                icon = Icons.Filled.Bolt,
                tint = Palette.Battery,
                backgroundTint = Palette.BatteryFill,
            )
        }
        if (system.isAcChargingOn) {
            StatusPill(
                label = "Grid charging",
                icon = Icons.Filled.Power,
                tint = Palette.Grid,
                backgroundTint = Palette.GridFill,
            )
        }
    }
}

private fun modeColors(mode: InverterMode): Triple<Color, Color, Color> = when (mode) {
    InverterMode.LINE -> Triple(Color(0x591D4ED8), Color(0xFFBFDBFE), Color(0xFF93C5FD))
    InverterMode.BATTERY -> Triple(Color(0x59047857), Color(0xFFA7F3D0), Color(0xFF6EE7B7))
    InverterMode.STANDBY -> Triple(Color(0x59334155), Color(0xFFE2E8F0), Color(0xFFCBD5E1))
    InverterMode.POWER_ON -> Triple(Color(0x590369A1), Color(0xFFBAE6FD), Color(0xFF7DD3FC))
    InverterMode.POWER_SAVING -> Triple(Color(0x593730A3), Color(0xFFC7D2FE), Color(0xFFA5B4FC))
    InverterMode.CHARGING -> Triple(Color(0x59B45309), Color(0xFFFDE68A), Color(0xFFFCD34D))
    InverterMode.FAULT -> Triple(Color(0x59B91C1C), Color(0xFFFECACA), Color(0xFFF87171))
    InverterMode.SHUTDOWN -> Triple(Color(0x5952525B), Color(0xFFE5E7EB), Color(0xFFD4D4D8))
}

@Composable
private fun WarningsBanner(warnings: List<InverterWarning>, onDismiss: () -> Unit) {
    val hasFault = warnings.any { it.severity == WarningSeverity.FAULT }
    val accent = if (hasFault) Color(0xFFFF6B6B) else Color(0xFFFFA726)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
            .background(accent.copy(alpha = 0.14f))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = accent)
        Column(Modifier.weight(1f)) {
            Text(
                if (hasFault) "${warnings.size} active fault${if (warnings.size == 1) "" else "s"}"
                else "${warnings.size} active warning${if (warnings.size == 1) "" else "s"}",
                color = Color.White,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                warnings.joinToString(" · ") { it.label },
                color = Color.White.copy(alpha = 0.9f),
                fontSize = 11.sp,
            )
        }
        IconButton(onClick = onDismiss) {
            Icon(Icons.Filled.Close, contentDescription = "Dismiss", tint = Color.White.copy(alpha = 0.7f))
        }
    }
}

/** Bottom-sheet host that dispatches to the right detail body per component. */
@Composable
private fun ComponentDetailSheet(
    vm: LiveDashboardViewModel,
    component: FlowComponent,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false)

    // Mirror iOS: only refresh if config is empty
    LaunchedEffect(component) {
        val needs = component == FlowComponent.BATTERY ||
                    component == FlowComponent.LOAD ||
                    component == FlowComponent.INVERTER
        if (needs && vm.config.value.isEmpty) {
            scope.launch { vm.refreshExtras() }
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Palette.BackgroundTop,
    ) {
        ComponentDetailBody(vm = vm, component = component, onDismiss = onDismiss)
    }
}
