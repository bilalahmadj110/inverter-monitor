package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.bilalahmad.invertermonitor.ui.theme.Palette

/**
 * Battery-shaped gauge that fills from the bottom based on SoC.
 * Green ≥50%, amber 20-50%, red <20% — matches iOS implementation.
 */
@Composable
fun BatteryGauge(percentage: Double, isActive: Boolean, modifier: Modifier = Modifier) {
    val clamped = (percentage.coerceIn(0.0, 100.0) / 100.0).toFloat()
    val targetColor = when {
        percentage < 20 -> Color(0xFFFF6B6B)
        percentage < 50 -> Color(0xFFFFA726)
        else -> Palette.Battery
    }
    val fill by animateFloatAsState(targetValue = clamped, animationSpec = tween(450), label = "battery-fill")
    val color by animateColorAsState(targetValue = targetColor, animationSpec = tween(250), label = "battery-color")
    val alphaOutline = if (isActive) 1f else 0.55f
    val alphaFill = if (isActive) 1f else 0.4f

    Box(modifier = modifier.fillMaxSize()) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            val terminalHeight = h * 0.08f
            val bodyHeight = h - terminalHeight
            val bodyWidth = w * 0.72f
            val terminalWidth = bodyWidth * 0.34f
            val leftX = (w - bodyWidth) / 2f
            val topY = terminalHeight
            val strokePx = 2.5.dp.toPx()
            val padPx = 3.dp.toPx()
            val cornerBody = CornerRadius(8.dp.toPx(), 8.dp.toPx())
            val cornerFill = CornerRadius(5.dp.toPx(), 5.dp.toPx())

            // Terminal cap
            drawRect(
                color = color.copy(alpha = alphaOutline),
                topLeft = Offset(w / 2f - terminalWidth / 2f, 0f),
                size = Size(terminalWidth, terminalHeight),
            )

            // Body translucent background
            drawRoundRect(
                color = Color.White.copy(alpha = 0.06f),
                topLeft = Offset(leftX, topY),
                size = Size(bodyWidth, bodyHeight),
                cornerRadius = cornerBody,
            )
            drawRoundRect(
                color = color.copy(alpha = alphaOutline),
                topLeft = Offset(leftX, topY),
                size = Size(bodyWidth, bodyHeight),
                style = Stroke(width = strokePx),
                cornerRadius = cornerBody,
            )

            // Fill from the bottom
            val fillWidth = (bodyWidth - 2 * padPx).coerceAtLeast(0f)
            val fillHeight = ((bodyHeight - 2 * padPx) * fill).coerceAtLeast(0f)
            if (fillHeight > 0f) {
                drawRoundRect(
                    color = color.copy(alpha = alphaFill),
                    topLeft = Offset(leftX + padPx, topY + bodyHeight - padPx - fillHeight),
                    size = Size(fillWidth, fillHeight),
                    cornerRadius = cornerFill,
                )
            }
        }
    }
}
