package com.bilalahmad.invertermonitor.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.ui.theme.Palette

/**
 * Shared chrome for every ModalBottomSheet in the app. A consistent header with a
 * tinted icon badge + title + subtitle + close button, then a vertically-scrollable
 * body with standardised padding.
 *
 * The sheet itself (ModalBottomSheet) is supplied by the caller — this scaffold is
 * just the *inside* so the sheet can keep its native drag handle, scrim, etc.
 */
@Composable
fun SheetScaffold(
    icon: ImageVector,
    iconTint: Color,
    title: String,
    subtitle: String,
    onDismiss: () -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp)
            .padding(top = 4.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        SheetHeader(icon, iconTint, title, subtitle, onDismiss)
        content()
    }
}

@Composable
private fun SheetHeader(
    icon: ImageVector,
    iconTint: Color,
    title: String,
    subtitle: String,
    onDismiss: () -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        // Icon badge with soft radial glow behind it — signals the component visually.
        Box(
            modifier = Modifier
                .size(56.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(
                    Brush.radialGradient(
                        colors = listOf(iconTint.copy(alpha = 0.28f), iconTint.copy(alpha = 0.10f)),
                    )
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(28.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(
                title,
                color = Color.White,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                subtitle,
                color = Palette.SubtleText,
                fontSize = 12.sp,
            )
        }
        IconButton(
            onClick = onDismiss,
            modifier = Modifier
                .size(34.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.06f)),
        ) {
            Icon(
                Icons.Filled.Close,
                contentDescription = "Close",
                tint = Palette.MutedText,
                modifier = Modifier.size(18.dp),
            )
        }
    }
}

/**
 * Section label used throughout bottom sheets — a small coloured accent bar + uppercase
 * title with letter-spacing. Visually groups content below it without needing a whole card.
 */
@Composable
fun SheetSectionHeader(
    title: String,
    accent: Color = Palette.Solar,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            modifier = Modifier
                .size(width = 3.dp, height = 12.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(accent)
        )
        Text(
            title.uppercase(),
            color = Color.White.copy(alpha = 0.85f),
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.2.sp,
        )
    }
}

/**
 * Container that wraps a block of content with the standard translucent card chrome
 * and a hair of inner padding. Use this around stat grids, info rows, etc.
 */
@Composable
fun SheetCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .card(cornerRadius = 16)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )
}
