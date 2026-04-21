package com.bilalahmad.invertermonitor.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColors = darkColorScheme(
    primary = Palette.Solar,
    onPrimary = Color.Black,
    secondary = Palette.Battery,
    tertiary = Palette.Grid,
    background = Palette.BackgroundTop,
    onBackground = Color.White,
    surface = Palette.CardSurface,
    onSurface = Color.White,
    surfaceVariant = Palette.CardSurface,
    onSurfaceVariant = Palette.MutedText,
    error = Color(0xFFFF6B6B),
    onError = Color.White,
)

@Composable
fun InverterMonitorTheme(
    @Suppress("UNUSED_PARAMETER") useDarkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    // The iOS app is dark-only (matches the web app). We lock to dark here too for
    // visual parity — light mode would need rethinking every gradient + glass panel.
    MaterialTheme(
        colorScheme = DarkColors,
        typography = AppTypography,
        content = content,
    )
}
