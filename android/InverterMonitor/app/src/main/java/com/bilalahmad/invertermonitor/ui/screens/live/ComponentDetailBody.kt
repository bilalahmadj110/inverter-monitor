package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.models.*
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.ui.components.InfoRow
import com.bilalahmad.invertermonitor.ui.components.SheetCard
import com.bilalahmad.invertermonitor.ui.components.SheetScaffold
import com.bilalahmad.invertermonitor.ui.components.SheetSectionHeader
import com.bilalahmad.invertermonitor.ui.components.StatTile
import com.bilalahmad.invertermonitor.ui.components.ToastBanner
import com.bilalahmad.invertermonitor.ui.components.ToastStyle
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlin.math.abs
import kotlin.math.roundToInt

@Composable
fun ComponentDetailBody(
    vm: LiveDashboardViewModel,
    component: FlowComponent,
    onDismiss: () -> Unit,
) {
    val status by vm.status.collectAsStateWithLifecycle()
    val config by vm.config.collectAsStateWithLifecycle()
    val priorityFlash by vm.priorityFlash.collectAsStateWithLifecycle()
    val priorityError by vm.priorityError.collectAsStateWithLifecycle()
    val isApplying by vm.isApplyingPriority.collectAsStateWithLifecycle()
    val isRefreshing by vm.isRefreshingExtras.collectAsStateWithLifecycle()

    val meta = remember(component) { componentMeta(component) }

    SheetScaffold(
        icon = meta.icon,
        iconTint = meta.tint,
        title = component.title,
        subtitle = meta.subtitle,
        onDismiss = onDismiss,
    ) {
        NowSection(component, status, meta.tint)
        when (component) {
            FlowComponent.SOLAR -> NotesCard(
                "PV settings on this inverter are read-only. Output / charger routing is controlled from the Load and Battery panels.",
                meta.tint,
            )
            FlowComponent.GRID -> NotesCard(
                "Grid-related write operations (input voltage range, AC charging current) aren't exposed yet. The readings above are live from the inverter.",
                meta.tint,
            )
            FlowComponent.LOAD -> LoadPrioritySection(vm, config, priorityFlash, priorityError, isApplying)
            FlowComponent.BATTERY -> {
                BatteryPrioritySection(vm, config, priorityFlash, priorityError, isApplying)
                BatteryInfoSection(config)
            }
            FlowComponent.INVERTER -> InverterConfigSection(vm, config, isRefreshing)
        }
    }
}

private data class ComponentMeta(val icon: ImageVector, val tint: Color, val subtitle: String)

private fun componentMeta(component: FlowComponent): ComponentMeta = when (component) {
    FlowComponent.SOLAR -> ComponentMeta(Icons.Filled.WbSunny, Palette.Solar, "Photovoltaic input")
    FlowComponent.GRID -> ComponentMeta(Icons.Filled.Power, Palette.Grid, "Utility grid")
    FlowComponent.BATTERY -> ComponentMeta(Icons.Filled.BatteryFull, Palette.Battery, "Energy storage")
    FlowComponent.LOAD -> ComponentMeta(Icons.Filled.Home, Palette.Load, "House consumption")
    FlowComponent.INVERTER -> ComponentMeta(Icons.Filled.BatteryChargingFull, Palette.InverterAmber, "Inverter system")
}

// ---------- Now section (live readings) -------------------------------------

@Composable
private fun NowSection(component: FlowComponent, status: InverterStatus, tint: Color) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("Now", accent = tint)
        val rows: List<Pair<StatData, StatData>> = nowStatPairs(component, status, tint)
        for ((a, b) in rows) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatTile(label = a.label, value = a.value, unit = a.unit, accent = a.accent, modifier = Modifier.weight(1f))
                StatTile(label = b.label, value = b.value, unit = b.unit, accent = b.accent, modifier = Modifier.weight(1f))
            }
        }
    }
}

private data class StatData(val label: String, val value: String, val unit: String? = null, val accent: Color = Color.White)

private fun nowStatPairs(
    component: FlowComponent,
    status: InverterStatus,
    tint: Color,
): List<Pair<StatData, StatData>> = when (component) {
    FlowComponent.SOLAR -> {
        val s = status.metrics.solar
        listOf(
            StatData("Power", "${s.power.roundToInt()}", "W", tint) to
                StatData("Voltage", "%.1f".format(s.voltage), "V"),
            StatData("Current", "%.2f".format(s.current), "A") to
                StatData("To Battery", "%.2f".format(s.pvToBatteryCurrent), "A"),
        )
    }
    FlowComponent.GRID -> {
        val g = status.metrics.grid
        listOf(
            StatData("Voltage", "${g.voltage.roundToInt()}", "V") to
                StatData("Frequency", "%.1f".format(g.frequency), "Hz"),
            StatData("Power", "${g.power.roundToInt()}", "W", tint) to
                StatData("Status", if (g.inUse) "In use" else "Idle"),
        )
    }
    FlowComponent.BATTERY -> {
        val b = status.metrics.battery
        listOf(
            StatData("State of Charge", "${b.percentage.roundToInt()}", "%", tint) to
                StatData("Voltage", "%.2f".format(b.voltage), "V"),
            StatData("Current", "%.2f".format(abs(b.current)), "A") to
                StatData("Direction", b.direction.label),
        )
    }
    FlowComponent.LOAD -> {
        val l = status.metrics.load
        listOf(
            StatData("Active Power", "${l.effectivePower.roundToInt()}", "W", tint) to
                StatData("Apparent", "${l.apparentPower.roundToInt()}", "VA"),
            StatData("Voltage", "${l.voltage.roundToInt()}", "V") to
                StatData("Load %", "${l.percentage.roundToInt()}", "%"),
        )
    }
    FlowComponent.INVERTER -> {
        val sys = status.system
        listOf(
            StatData("Temperature", if (sys.temperature > 0) "${sys.temperature.roundToInt()}" else "—", "°C") to
                StatData("Bus Voltage", if (sys.busVoltage > 0) "${sys.busVoltage.roundToInt()}" else "—", "V"),
            StatData("Mode", sys.modeLabel.ifEmpty { sys.mode.defaultLabel }, accent = tint) to
                StatData("Charge Stage", sys.chargeStage.label),
        )
    }
}

// ---------- Notes card ------------------------------------------------------

@Composable
private fun NotesCard(text: String, tint: Color) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("About", accent = tint)
        SheetCard {
            Text(
                text,
                color = Palette.MutedText,
                fontSize = 12.sp,
                lineHeight = 18.sp,
            )
        }
    }
}

// ---------- Priority chooser (shared shape) ---------------------------------

private data class PriorityRow(val key: String, val title: String, val detail: String, val icon: ImageVector)

@Composable
private fun PriorityChoiceCard(
    title: String,
    detail: String,
    icon: ImageVector,
    isCurrent: Boolean,
    isBusy: Boolean,
    enabled: Boolean,
    accent: Color,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(14.dp)
    val bg = if (isCurrent) accent.copy(alpha = 0.14f) else Color.White.copy(alpha = 0.04f)
    val borderColor = if (isCurrent) accent.copy(alpha = 0.55f) else Palette.CardBorder
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(bg)
            .border(1.dp, borderColor, shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // Leading icon chip — gives each mode a glanceable identity.
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(accent.copy(alpha = if (isCurrent) 0.22f else 0.12f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = null, tint = accent, modifier = Modifier.size(18.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Text(detail, color = Palette.SubtleText, fontSize = 11.sp, lineHeight = 15.sp)
        }
        when {
            isBusy -> CircularProgressIndicator(
                color = accent, strokeWidth = 2.dp, modifier = Modifier.size(18.dp),
            )
            isCurrent -> Box(
                modifier = Modifier
                    .size(24.dp)
                    .clip(CircleShape)
                    .background(accent),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.Check, contentDescription = "Applied",
                    tint = Color.White, modifier = Modifier.size(14.dp),
                )
            }
            else -> Icon(
                Icons.Filled.ChevronRight, contentDescription = null, tint = Palette.SubtleText,
            )
        }
    }
}

// ---------- Load priority ---------------------------------------------------

@Composable
private fun LoadPrioritySection(
    vm: LiveDashboardViewModel,
    config: InverterConfig,
    flash: String?,
    error: String?,
    isApplying: Boolean,
) {
    var pending by remember { mutableStateOf<OutputPriority?>(null) }
    val rows = remember {
        listOf(
            PriorityRow(OutputPriority.SBU.name, OutputPriority.SBU.title, OutputPriority.SBU.detail, Icons.Filled.SolarPower),
            PriorityRow(OutputPriority.SOL.name, OutputPriority.SOL.title, OutputPriority.SOL.detail, Icons.Filled.WbSunny),
            PriorityRow(OutputPriority.UTI.name, OutputPriority.UTI.title, OutputPriority.UTI.detail, Icons.Filled.Power),
        )
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("Output Priority", accent = Palette.Load)
        Text(
            "Which source drives the load. Current: ${config.outputPriority?.shortLabel ?: "—"}",
            color = Palette.MutedText,
            fontSize = 11.sp,
        )
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (row in rows) {
                PriorityChoiceCard(
                    title = row.title, detail = row.detail, icon = row.icon,
                    isCurrent = config.outputPriority?.name == row.key,
                    isBusy = isApplying && pending?.name == row.key,
                    enabled = !isApplying,
                    accent = Palette.Load,
                    onClick = { pending = OutputPriority.valueOf(row.key) },
                )
            }
        }
        StatusToast(flash = flash, error = error)
    }

    pending?.let { mode ->
        AlertDialog(
            onDismissRequest = { pending = null },
            title = { Text("Apply ${mode.title}?") },
            text = { Text(mode.detail) },
            confirmButton = {
                TextButton(onClick = { vm.setOutputPriority(mode); pending = null }) {
                    Text("Apply", color = Palette.Load)
                }
            },
            dismissButton = { TextButton(onClick = { pending = null }) { Text("Cancel") } },
            containerColor = Palette.BackgroundMid,
            titleContentColor = Color.White,
            textContentColor = Palette.MutedText,
        )
    }
}

// ---------- Charger priority ------------------------------------------------

@Composable
private fun BatteryPrioritySection(
    vm: LiveDashboardViewModel,
    config: InverterConfig,
    flash: String?,
    error: String?,
    isApplying: Boolean,
) {
    var pending by remember { mutableStateOf<ChargerPriority?>(null) }
    val rows = remember {
        listOf(
            PriorityRow(ChargerPriority.SOL_ONLY.name, ChargerPriority.SOL_ONLY.title, ChargerPriority.SOL_ONLY.detail, Icons.Filled.WbSunny),
            PriorityRow(ChargerPriority.SOL_FIRST.name, ChargerPriority.SOL_FIRST.title, ChargerPriority.SOL_FIRST.detail, Icons.Filled.SolarPower),
            PriorityRow(ChargerPriority.SOL_UTI.name, ChargerPriority.SOL_UTI.title, ChargerPriority.SOL_UTI.detail, Icons.Filled.Bolt),
            PriorityRow(ChargerPriority.UTI_SOL.name, ChargerPriority.UTI_SOL.title, ChargerPriority.UTI_SOL.detail, Icons.Filled.Power),
        )
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("Charger Priority", accent = Palette.Battery)
        Text(
            "What's allowed to charge the battery. Current: ${config.chargerPriority?.title ?: "—"}",
            color = Palette.MutedText,
            fontSize = 11.sp,
        )
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (row in rows) {
                PriorityChoiceCard(
                    title = row.title, detail = row.detail, icon = row.icon,
                    isCurrent = config.chargerPriority?.name == row.key,
                    isBusy = isApplying && pending?.name == row.key,
                    enabled = !isApplying,
                    accent = Palette.Battery,
                    onClick = { pending = ChargerPriority.valueOf(row.key) },
                )
            }
        }
        StatusToast(flash = flash, error = error)
    }

    pending?.let { mode ->
        AlertDialog(
            onDismissRequest = { pending = null },
            title = { Text("Apply ${mode.title}?") },
            text = { Text(mode.detail) },
            confirmButton = {
                TextButton(onClick = { vm.setChargerPriority(mode); pending = null }) {
                    Text("Apply", color = Palette.Battery)
                }
            },
            dismissButton = { TextButton(onClick = { pending = null }) { Text("Cancel") } },
            containerColor = Palette.BackgroundMid,
            titleContentColor = Color.White,
            textContentColor = Palette.MutedText,
        )
    }
}

@Composable
private fun StatusToast(flash: String?, error: String?) {
    AnimatedVisibility(visible = flash != null, enter = fadeIn(), exit = fadeOut()) {
        flash?.let { ToastBanner(it, ToastStyle.SUCCESS) }
    }
    AnimatedVisibility(visible = error != null, enter = fadeIn(), exit = fadeOut()) {
        error?.let { ToastBanner(it, ToastStyle.ERROR) }
    }
}

// ---------- Battery info ----------------------------------------------------

@Composable
private fun BatteryInfoSection(config: InverterConfig) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("Battery", accent = Palette.Battery)
        SheetCard {
            InfoRow("Type", config.batteryType ?: "—")
            InfoRow("Max Charging Current", fmt(config.maxChargingCurrent, "A"))
            InfoRow("Max AC Charging Current", fmt(config.maxAcChargingCurrent, "A"))
            InfoRow("Under Voltage", fmt(config.batteryUnderVoltage, "V"))
            InfoRow("Bulk Charge", fmt(config.batteryBulkChargeVoltage, "V"))
            InfoRow("Float Charge", fmt(config.batteryFloatChargeVoltage, "V"))
        }
    }
}

// ---------- Inverter full config --------------------------------------------

@Composable
private fun InverterConfigSection(vm: LiveDashboardViewModel, config: InverterConfig, isRefreshing: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetSectionHeader("Configuration (QPIRI)", accent = Palette.InverterAmber)
        SheetCard {
            if (config.rows.isEmpty()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (isRefreshing) {
                        CircularProgressIndicator(
                            color = Palette.InverterAmber, strokeWidth = 2.dp, modifier = Modifier.size(14.dp),
                        )
                    }
                    Text(
                        if (isRefreshing) "Reading from inverter…" else "No config loaded — tap Refresh below.",
                        color = Palette.MutedText,
                        fontSize = 12.sp,
                    )
                }
            } else {
                for (row in config.rows) {
                    InfoRow(row.label, if (row.unit.isEmpty()) row.value else "${row.value} ${row.unit}")
                }
            }
        }

        Button(
            onClick = { vm.requestRefreshExtras() },
            modifier = Modifier.fillMaxWidth().height(48.dp),
            enabled = !isRefreshing,
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Palette.InverterAmber.copy(alpha = 0.2f),
                contentColor = Palette.InverterAmber,
                disabledContainerColor = Palette.InverterAmber.copy(alpha = 0.1f),
                disabledContentColor = Palette.InverterAmber.copy(alpha = 0.6f),
            ),
        ) {
            if (isRefreshing) {
                CircularProgressIndicator(
                    color = Palette.InverterAmber, strokeWidth = 2.dp, modifier = Modifier.size(16.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text("Refreshing…", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            } else {
                Icon(Icons.Filled.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Refresh configuration", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

private fun fmt(value: Double?, unit: String): String {
    if (value == null) return "—"
    if (value == value.toLong().toDouble()) return "${value.toLong()} $unit"
    return "%.1f %s".format(value, unit)
}
