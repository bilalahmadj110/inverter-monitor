package com.bilalahmad.invertermonitor.ui.screens.live

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.data.models.DailySummary
import com.bilalahmad.invertermonitor.data.models.MonthlyStats
import com.bilalahmad.invertermonitor.data.models.YearlyStats
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import kotlin.math.roundToInt

private enum class Period(val title: String) {
    TODAY("Today"), MONTH("This Month"), YEAR("This Year")
}

@Composable
fun TodaySummarySection(
    summary: DailySummary,
    monthStats: MonthlyStats?,
    yearStats: YearlyStats?,
) {
    var period by remember { mutableStateOf(Period.TODAY) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .card()
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(period.title, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
                 modifier = Modifier.weight(1f))
            Text(dateSubtitle(period, summary, monthStats, yearStats), color = Palette.SubtleText, fontSize = 11.sp)
        }

        SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
            Period.entries.forEachIndexed { index, p ->
                SegmentedButton(
                    selected = period == p,
                    onClick = { period = p },
                    shape = SegmentedButtonDefaults.itemShape(index, Period.entries.size),
                    colors = SegmentedButtonDefaults.colors(
                        activeContainerColor = Palette.Solar.copy(alpha = 0.3f),
                        activeContentColor = Color.White,
                        inactiveContainerColor = Color.Transparent,
                        inactiveContentColor = Palette.MutedText,
                    ),
                    label = { Text(p.title) },
                )
            }
        }

        val (solar, grid, load, charge, discharge) = activeValues(period, summary, monthStats, yearStats)

        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SummaryTile("Solar", Palette.Solar, kwhFmt(solar), modifier = Modifier.weight(1f))
                SummaryTile("Grid Import", Palette.Grid, kwhFmt(grid), modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SummaryTile("Load", Palette.Load, kwhFmt(load), modifier = Modifier.weight(1f))
                ChargeDischargeTile(charge, discharge, modifier = Modifier.weight(1f))
            }
            if (period == Period.TODAY) {
                SelfSufficiencyTile(summary)
            }
        }
    }
}

private data class PeriodValues(
    val solar: Double,
    val grid: Double,
    val load: Double,
    val charge: Double,
    val discharge: Double,
)

private fun activeValues(period: Period, s: DailySummary, m: MonthlyStats?, y: YearlyStats?): PeriodValues {
    return when (period) {
        Period.TODAY -> PeriodValues(s.solarKwh, s.gridKwh, s.loadKwh, s.batteryChargeKwh, s.batteryDischargeKwh)
        Period.MONTH -> PeriodValues(
            (m?.solarEnergyWh ?: 0.0) / 1000.0,
            (m?.gridEnergyWh ?: 0.0) / 1000.0,
            (m?.loadEnergyWh ?: 0.0) / 1000.0,
            (m?.batteryChargeEnergyWh ?: 0.0) / 1000.0,
            (m?.batteryDischargeEnergyWh ?: 0.0) / 1000.0,
        )
        Period.YEAR -> PeriodValues(
            (y?.solarEnergyWh ?: 0.0) / 1000.0,
            (y?.gridEnergyWh ?: 0.0) / 1000.0,
            (y?.loadEnergyWh ?: 0.0) / 1000.0,
            (y?.batteryChargeEnergyWh ?: 0.0) / 1000.0,
            (y?.batteryDischargeEnergyWh ?: 0.0) / 1000.0,
        )
    }
}

private fun dateSubtitle(p: Period, s: DailySummary, m: MonthlyStats?, y: YearlyStats?): String = when (p) {
    Period.TODAY -> s.date ?: "—"
    Period.MONTH -> m?.month ?: SimpleDateFormat("yyyy-MM", Locale.US).format(java.util.Date())
    Period.YEAR -> y?.year ?: Calendar.getInstance().get(Calendar.YEAR).toString()
}

private fun kwhFmt(v: Double) = String.format(Locale.US, "%.2f", v)

@Composable
private fun SummaryTile(title: String, tint: Color, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Palette.CardSurface.copy(alpha = 0.6f))
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(title, color = tint, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(4.dp))
            Text("kWh", color = Palette.SubtleText, fontSize = 11.sp)
        }
    }
}

@Composable
private fun ChargeDischargeTile(charge: Double, discharge: Double, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Palette.CardSurface.copy(alpha = 0.6f))
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text("Bat. Charge / Discharge", color = Palette.Battery, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Text("${kwhFmt(charge)} / ${kwhFmt(discharge)} kWh",
             color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun SelfSufficiencyTile(summary: DailySummary) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Palette.CardSurface.copy(alpha = 0.6f))
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text("Self-Sufficiency", color = Color(0xFF4ADE80), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Row(verticalAlignment = Alignment.Bottom) {
            Text("${(summary.selfSufficiency * 100).roundToInt()}",
                 color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(4.dp))
            Text("%", color = Palette.SubtleText, fontSize = 11.sp)
        }
        Text("Solar share ${(summary.solarFraction * 100).roundToInt()}%",
             color = Palette.SubtleText, fontSize = 10.sp)
    }
}
