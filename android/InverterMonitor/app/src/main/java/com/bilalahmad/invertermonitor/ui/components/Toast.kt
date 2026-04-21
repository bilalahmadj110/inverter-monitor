package com.bilalahmad.invertermonitor.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

enum class ToastStyle(val accent: Color, val icon: androidx.compose.ui.graphics.vector.ImageVector) {
    SUCCESS(Color(0xFF34D399), Icons.Filled.CheckCircle),
    ERROR(Color(0xFFFF6B6B), Icons.Filled.Warning),
    INFO(Color(0xFF60A5FA), Icons.Filled.Info),
}

@Composable
fun ToastBanner(message: String, style: ToastStyle, modifier: Modifier = Modifier) {
    val accent = style.accent
    val shape = RoundedCornerShape(10.dp)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(shape)
            .background(accent.copy(alpha = 0.12f))
            .border(BorderStroke(1.dp, accent.copy(alpha = 0.4f)), shape)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(style.icon, contentDescription = null, tint = accent, modifier = Modifier.size(18.dp))
        Text(message, color = accent, fontSize = 13.sp)
    }
}
