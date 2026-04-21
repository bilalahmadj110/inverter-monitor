package com.bilalahmad.invertermonitor.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.ui.theme.Palette

/** Standard glassy card chrome used throughout the app. */
fun Modifier.card(cornerRadius: Int = 14): Modifier = this
    .clip(RoundedCornerShape(cornerRadius.dp))
    .background(Palette.CardSurface)
    .border(BorderStroke(1.dp, Palette.CardBorder), RoundedCornerShape(cornerRadius.dp))

/**
 * Small labelled stat tile used inside component detail sheets and elsewhere.
 * A muted-white backdrop, compact tracking on the label, and proper baseline
 * alignment between the number and its unit.
 */
@Composable
fun StatTile(
    label: String,
    value: String,
    unit: String? = null,
    accent: Color = Color.White,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(14.dp))
            .background(Palette.CardSurface.copy(alpha = 0.7f))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text = label,
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            color = Palette.SubtleText,
            letterSpacing = 0.5.sp,
        )
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                text = value,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = accent,
            )
            if (unit != null) {
                Spacer(Modifier.width(3.dp))
                Text(
                    text = unit,
                    fontSize = 11.sp,
                    color = Palette.SubtleText,
                    modifier = Modifier.padding(bottom = 3.dp),
                )
            }
        }
    }
}

/** Label : value row with bottom divider. */
@Composable
fun InfoRow(label: String, value: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, fontSize = 12.sp, color = Palette.MutedText, modifier = Modifier.weight(1f))
        Text(
            value,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = Color.White,
            textAlign = TextAlign.End,
        )
    }
}
