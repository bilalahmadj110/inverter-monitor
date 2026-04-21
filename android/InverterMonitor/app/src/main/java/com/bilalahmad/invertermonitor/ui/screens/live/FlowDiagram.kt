package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.data.models.BatteryDirection
import com.bilalahmad.invertermonitor.data.models.InverterStatus
import com.bilalahmad.invertermonitor.ui.theme.Palette
import kotlin.math.roundToInt

enum class FlowComponent(val title: String) {
    SOLAR("Solar"), GRID("Grid"), BATTERY("Battery"), LOAD("Load"), INVERTER("Inverter")
}

/**
 * Diamond-shaped flow diagram. Four corner nodes (Grid/Load/Solar/Battery) connect
 * to a central Inverter via animated dashed lines with gliding particles.
 *
 * Layout: each corner is a vertical stack (icon on top, 2 text lines below), anchored
 * at a fixed inset from its edge. Vertical stacks keep each corner narrow enough to
 * never overlap even on 360-dp phones, and the icon center lines up exactly with the
 * line endpoint so the dashed lines meet the icon edge cleanly.
 */
@Composable
fun FlowDiagram(status: InverterStatus, onTap: (FlowComponent) -> Unit) {
    val infinite = rememberInfiniteTransition(label = "flow-phase")
    val dashPhase by infinite.animateFloat(
        initialValue = 0f,
        targetValue = 28f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing), RepeatMode.Restart),
        label = "dashPhase",
    )
    val particlePhase by infinite.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2000, easing = LinearEasing), RepeatMode.Restart),
        label = "particle",
    )

    val density = LocalDensity.current

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxWidth()
            .height(340.dp)
            .padding(vertical = 6.dp)
    ) {
        val widthPx = with(density) { maxWidth.toPx() }
        val heightPx = with(density) { maxHeight.toPx() }

        // How far inside each edge the corner icons sit. 60 dp works from 360-dp up.
        val edgeInset = with(density) { 60.dp.toPx() }
        val iconRadius = with(density) { 28.dp.toPx() }  // icon is 56 dp

        // Put the corners a little higher/lower than top/bottom to leave room for
        // the two text lines beneath each icon.
        val topRowY = with(density) { 46.dp.toPx() }
        val botRowY = heightPx - with(density) { 70.dp.toPx() }

        // Icon centre positions — line endpoints also land exactly here.
        val gridCenter    = Offset(edgeInset, topRowY)
        val loadCenter    = Offset(widthPx - edgeInset, topRowY)
        val solarCenter   = Offset(edgeInset, botRowY)
        val batteryCenter = Offset(widthPx - edgeInset, botRowY)

        // Inverter sits in the geometric centre; lines point to just outside its disc.
        val invCenter = Offset(widthPx / 2f, heightPx / 2f)
        val invRadius = with(density) { 46.dp.toPx() }

        // Line endpoints pull slightly in from the icon centre so the line visually
        // meets the icon's edge (iconRadius) rather than passing through its middle.
        fun iconEdge(from: Offset, to: Offset): Offset {
            val dx = to.x - from.x
            val dy = to.y - from.y
            val len = kotlin.math.sqrt(dx * dx + dy * dy).coerceAtLeast(0.001f)
            return Offset(from.x + dx / len * iconRadius, from.y + dy / len * iconRadius)
        }

        // --- Lines + particles layer ---
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawLink(gridCenter, invCenter, Palette.Grid,
                     active = status.metrics.grid.inUse,
                     reversed = false,
                     iconEdgeStart = iconEdge(gridCenter, invCenter),
                     iconEdgeEnd = iconEdge(invCenter, gridCenter),
                     dashPhase = dashPhase, particlePhase = particlePhase)
            drawLink(loadCenter, invCenter, Palette.Load,
                     active = status.metrics.load.effectivePower > 5,
                     reversed = false,
                     iconEdgeStart = iconEdge(loadCenter, invCenter),
                     iconEdgeEnd = iconEdge(invCenter, loadCenter),
                     dashPhase = dashPhase, particlePhase = particlePhase,
                     // Load flow is from inverter → load, so particle should travel that way.
                     particleFrom = iconEdge(invCenter, loadCenter),
                     particleTo = iconEdge(loadCenter, invCenter))
            drawLink(solarCenter, invCenter, Palette.Solar,
                     active = status.metrics.solar.power > 5,
                     reversed = false,
                     iconEdgeStart = iconEdge(solarCenter, invCenter),
                     iconEdgeEnd = iconEdge(invCenter, solarCenter),
                     dashPhase = dashPhase, particlePhase = particlePhase)
            val batteryActive = status.metrics.battery.direction != BatteryDirection.IDLE
            val batteryReversed = status.metrics.battery.direction == BatteryDirection.CHARGING
            drawLink(batteryCenter, invCenter, Palette.Battery,
                     active = batteryActive,
                     reversed = batteryReversed,
                     iconEdgeStart = iconEdge(batteryCenter, invCenter),
                     iconEdgeEnd = iconEdge(invCenter, batteryCenter),
                     dashPhase = dashPhase, particlePhase = particlePhase,
                     particleFrom = if (batteryReversed) iconEdge(invCenter, batteryCenter)
                                     else iconEdge(batteryCenter, invCenter),
                     particleTo = if (batteryReversed) iconEdge(batteryCenter, invCenter)
                                   else iconEdge(invCenter, batteryCenter))
        }

        // --- Corner nodes ---
        CornerNode(
            component = FlowComponent.GRID,
            iconCenter = gridCenter,
            primary = "${status.metrics.grid.voltage.roundToInt()} V",
            secondary = "%.1f Hz".format(status.metrics.grid.frequency),
            active = status.metrics.grid.inUse,
            onClick = { onTap(FlowComponent.GRID) },
        )
        CornerNode(
            component = FlowComponent.LOAD,
            iconCenter = loadCenter,
            primary = "${status.metrics.load.effectivePower.roundToInt()} W",
            secondary = "${status.metrics.load.voltage.roundToInt()} V · ${status.metrics.load.percentage.roundToInt()}%",
            active = status.metrics.load.effectivePower > 5,
            onClick = { onTap(FlowComponent.LOAD) },
        )
        CornerNode(
            component = FlowComponent.SOLAR,
            iconCenter = solarCenter,
            primary = "${status.metrics.solar.power.roundToInt()} W",
            secondary = "%.1f V".format(status.metrics.solar.voltage),
            active = status.metrics.solar.power > 5,
            onClick = { onTap(FlowComponent.SOLAR) },
        )
        CornerNode(
            component = FlowComponent.BATTERY,
            iconCenter = batteryCenter,
            primary = "${status.metrics.battery.percentage.roundToInt()}%",
            secondary = "%.1f V".format(status.metrics.battery.voltage),
            active = status.metrics.battery.voltage > 20,
            batteryPercentage = status.metrics.battery.percentage,
            onClick = { onTap(FlowComponent.BATTERY) },
        )

        // --- Inverter (centre) ---
        val invTempLabel = if (status.system.temperature <= 0.0) "—°C"
                           else "${status.system.temperature.roundToInt()}°C"
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .offset {
                    IntOffset(
                        (invCenter.x - with(density) { 50.dp.toPx() }).toInt(),
                        (invCenter.y - with(density) { 60.dp.toPx() }).toInt(),
                    )
                }
                .width(100.dp)
                .clickable { onTap(FlowComponent.INVERTER) },
        ) {
            Box(
                modifier = Modifier
                    .size(92.dp)
                    .clip(CircleShape)
                    .background(Palette.InverterAmber.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.BatteryChargingFull,
                    contentDescription = "Inverter",
                    tint = Palette.InverterAmber,
                    modifier = Modifier.size(36.dp),
                )
            }
            Text(
                invTempLabel,
                fontSize = 11.sp,
                color = Color.White.copy(alpha = 0.75f),
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

/**
 * A single corner node: icon (56 dp) on top, two short text lines centred below.
 * Total footprint is about 72 × 92 dp — narrow enough to never collide on 360-dp phones.
 *
 * `iconCenter` is the screen-relative centre of the 56-dp icon; all text is centred
 * on the same X so the whole column looks like a single unit.
 */
@Composable
private fun CornerNode(
    component: FlowComponent,
    iconCenter: Offset,
    primary: String,
    secondary: String,
    active: Boolean,
    batteryPercentage: Double = 0.0,
    onClick: () -> Unit,
) {
    val density = LocalDensity.current
    val nodeWidthDp = 84.dp
    val nodeWidthPx = with(density) { nodeWidthDp.toPx() }
    val iconRadiusPx = with(density) { 28.dp.toPx() }

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .offset {
                IntOffset(
                    (iconCenter.x - nodeWidthPx / 2f).toInt(),
                    (iconCenter.y - iconRadiusPx).toInt(),
                )
            }
            .width(nodeWidthDp)
            .clickable(onClick = onClick),
    ) {
        ComponentIcon(component, active, batteryPercentage)
        Text(
            primary,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            color = Color.White,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp),
        )
        Text(
            secondary,
            fontSize = 10.sp,
            color = Palette.SubtleText,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun ComponentIcon(component: FlowComponent, active: Boolean, batteryPercentage: Double) {
    val tint = when (component) {
        FlowComponent.SOLAR -> Palette.Solar
        FlowComponent.GRID -> Palette.Grid
        FlowComponent.BATTERY -> Palette.Battery
        FlowComponent.LOAD -> Palette.Load
        FlowComponent.INVERTER -> Palette.InverterAmber
    }
    val opacity = if (active) 1f else 0.55f
    Box(modifier = Modifier.size(56.dp), contentAlignment = Alignment.Center) {
        if (component == FlowComponent.BATTERY) {
            BatteryGauge(
                percentage = batteryPercentage,
                isActive = active,
                modifier = Modifier.size(40.dp, 52.dp),
            )
        } else {
            Box(
                modifier = Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(tint.copy(alpha = if (active) 0.22f else 0.10f)),
                contentAlignment = Alignment.Center,
            ) {
                val icon: ImageVector = when (component) {
                    FlowComponent.SOLAR -> Icons.Filled.WbSunny
                    FlowComponent.GRID -> Icons.Filled.Power
                    FlowComponent.LOAD -> Icons.Filled.Home
                    FlowComponent.INVERTER -> Icons.Filled.BatteryChargingFull
                    FlowComponent.BATTERY -> Icons.Filled.BatteryFull
                }
                Icon(
                    icon, contentDescription = null,
                    tint = tint.copy(alpha = opacity),
                    modifier = Modifier.size(26.dp),
                )
            }
        }
        // Active dot in the top-right.
        Box(
            modifier = Modifier
                .size(10.dp)
                .offset(x = 19.dp, y = (-19).dp)
                .clip(CircleShape)
                .background(if (active) Color(0xFF34D399) else Color.Gray),
        )
    }
}

/** Draws a single dashed line from `from.iconEdge` to `to.iconEdge` plus a gliding
 *  particle when active. `reversed` flips the dash animation direction. */
private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawLink(
    from: Offset,
    to: Offset,
    color: Color,
    active: Boolean,
    reversed: Boolean,
    iconEdgeStart: Offset,
    iconEdgeEnd: Offset,
    dashPhase: Float,
    particlePhase: Float,
    particleFrom: Offset = iconEdgeStart,
    particleTo: Offset = iconEdgeEnd,
) {
    val baseAlpha = if (active) 1f else 0.35f
    val pathEffect = if (active)
        PathEffect.dashPathEffect(
            floatArrayOf(8.dp.toPx(), 6.dp.toPx()),
            phase = if (reversed) -dashPhase else dashPhase,
        )
    else
        PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 4.dp.toPx()), 0f)

    drawLine(
        color = color.copy(alpha = baseAlpha),
        start = iconEdgeStart,
        end = iconEdgeEnd,
        strokeWidth = 4.dp.toPx(),
        cap = StrokeCap.Round,
        pathEffect = pathEffect,
    )

    if (active) {
        val t = particlePhase.coerceIn(0f, 1f)
        val px = particleFrom.x + (particleTo.x - particleFrom.x) * t
        val py = particleFrom.y + (particleTo.y - particleFrom.y) * t
        // Glow halo
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(color, color.copy(alpha = 0f)),
                center = Offset(px, py),
                radius = 14.dp.toPx(),
            ),
            radius = 14.dp.toPx(),
            center = Offset(px, py),
        )
        drawCircle(color = color, radius = 3.5.dp.toPx(), center = Offset(px, py))
    }
}
