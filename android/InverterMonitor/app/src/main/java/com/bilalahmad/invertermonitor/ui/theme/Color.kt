package com.bilalahmad.invertermonitor.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/**
 * One-for-one port of iOS's `Palette` enum. Kept as plain vals so Compose can
 * inline them into draw calls without allocating.
 */
object Palette {
    // Series colors (match iOS exactly)
    val Solar = Color(0xFFFCD34D)
    val SolarFill = Color(0x38FCD34D)
    val Grid = Color(0xFF60A5FA)
    val GridFill = Color(0x3860A5FA)
    val Load = Color(0xFFA78BFA)
    val LoadFill = Color(0x38A78BFA)
    val Battery = Color(0xFF34D399)
    val BatteryFill = Color(0x3834D399)

    val InverterAmber = Color(0xFFFBBF24)

    // Background gradient stops
    val BackgroundTop = Color(0xFF0F172A)
    val BackgroundMid = Color(0xFF0D1F3D)
    val BackgroundBottom = Color(0xFF191A4D)

    val CardSurface = Color(0x14FFFFFF)    // 8% white
    val CardBorder = Color(0x1FFFFFFF)     // 12% white
    val Divider = Color(0x14FFFFFF)        // 8% white

    // Text colors at various opacities
    val SubtleText = Color(0x8CFFFFFF)     // ~55%
    val MutedText = Color(0xBFFFFFFF)      // ~75%

    val BackgroundGradient: Brush
        get() = Brush.linearGradient(
            colors = listOf(BackgroundTop, BackgroundMid, BackgroundBottom),
            // start top-leading → end bottom-trailing (same as iOS immersiveBackground)
        )
}
