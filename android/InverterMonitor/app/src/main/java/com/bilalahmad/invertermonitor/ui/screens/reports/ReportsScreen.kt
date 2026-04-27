package com.bilalahmad.invertermonitor.ui.screens.reports

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bilalahmad.invertermonitor.data.viewmodels.LoadPhase
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsTab
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette

@Composable
fun ReportsScreen(vm: ReportsViewModel) {
    var tab by remember { mutableStateOf(ReportsTab.DAY) }

    LaunchedEffect(tab) {
        when (tab) {
            ReportsTab.DAY -> vm.loadDay()
            ReportsTab.MONTH -> vm.loadMonth()
            ReportsTab.YEAR -> vm.loadYear()
            ReportsTab.OUTAGES -> vm.loadOutages()
            ReportsTab.RAW -> vm.loadRaw()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Palette.BackgroundGradient)
            .padding(horizontal = 16.dp)
            .padding(top = 24.dp),
    ) {
        Text(
            "Reports",
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            modifier = Modifier.padding(bottom = 16.dp),
        )

        SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
            ReportsTab.entries.forEachIndexed { index, t ->
                SegmentedButton(
                    selected = tab == t,
                    onClick = { tab = t },
                    shape = SegmentedButtonDefaults.itemShape(index, ReportsTab.entries.size),
                    colors = SegmentedButtonDefaults.colors(
                        activeContainerColor = Palette.Solar.copy(alpha = 0.3f),
                        activeContentColor = Color.White,
                        inactiveContainerColor = Color.Transparent,
                        inactiveContentColor = Palette.MutedText,
                    ),
                    label = { Text(t.title, fontSize = 12.sp) },
                )
            }
        }

        Spacer(Modifier.height(16.dp))

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(bottom = 32.dp),
        ) {
            when (tab) {
                ReportsTab.DAY -> DayReport(vm)
                ReportsTab.MONTH -> MonthReport(vm)
                ReportsTab.YEAR -> YearReport(vm)
                ReportsTab.OUTAGES -> OutagesReport(vm)
                ReportsTab.RAW -> RawReadings(vm)
            }
        }
    }
}

@Composable
internal fun PhaseIndicator(phase: LoadPhase) {
    when (phase) {
        is LoadPhase.Loading -> Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.padding(vertical = 4.dp),
        ) {
            CircularProgressIndicator(
                color = Palette.SubtleText,
                strokeWidth = 2.dp,
                modifier = Modifier.size(14.dp),
            )
            Text("Loading…", color = Palette.SubtleText, fontSize = 11.sp)
        }
        is LoadPhase.Empty -> Text(
            "No data for this range",
            color = Palette.SubtleText,
            fontSize = 11.sp,
            modifier = Modifier.padding(vertical = 4.dp),
        )
        is LoadPhase.Error -> Text(
            phase.message,
            color = Color(0xFFFF6B6B),
            fontSize = 11.sp,
            modifier = Modifier.padding(vertical = 4.dp),
        )
        else -> {}
    }
}

@Composable
internal fun SummaryKpi(title: String, tint: Color, value: String, subtitle: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .card()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(title, color = tint, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Text(value, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(subtitle, color = Palette.SubtleText, fontSize = 10.sp)
    }
}
