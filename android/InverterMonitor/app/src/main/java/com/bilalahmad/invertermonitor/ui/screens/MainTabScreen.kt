package com.bilalahmad.invertermonitor.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.bilalahmad.invertermonitor.data.viewmodels.AuthViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.screens.live.LiveDashboardScreen
import com.bilalahmad.invertermonitor.ui.screens.reports.ReportsScreen
import com.bilalahmad.invertermonitor.ui.theme.Palette

private enum class Tab(val title: String) {
    LIVE("Live"), REPORTS("Reports"), SETTINGS("Settings")
}

@Composable
fun MainTabScreen(
    authVM: AuthViewModel,
    liveVM: LiveDashboardViewModel,
    reportsVM: ReportsViewModel,
) {
    var tab by remember { mutableStateOf(Tab.LIVE) }

    Scaffold(
        bottomBar = {
            NavigationBar(
                containerColor = Palette.BackgroundTop.copy(alpha = 0.95f),
                contentColor = Color.White,
            ) {
                for (t in Tab.entries) {
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = {
                            val icon = when (t) {
                                Tab.LIVE -> Icons.Filled.FlashOn
                                Tab.REPORTS -> Icons.AutoMirrored.Filled.ShowChart
                                Tab.SETTINGS -> Icons.Filled.Settings
                            }
                            Icon(icon, contentDescription = t.title)
                        },
                        label = { Text(t.title) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Palette.Solar,
                            selectedTextColor = Palette.Solar,
                            unselectedIconColor = Palette.MutedText,
                            unselectedTextColor = Palette.MutedText,
                            indicatorColor = Color.Transparent,
                        ),
                    )
                }
            }
        },
        containerColor = Color.Transparent,
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(Palette.BackgroundGradient)
        ) {
            when (tab) {
                Tab.LIVE -> LiveDashboardScreen(liveVM)
                Tab.REPORTS -> ReportsScreen(reportsVM)
                Tab.SETTINGS -> SettingsScreen(authVM, liveVM) { reportsVM.invalidateHistoryCache() }
            }
        }
    }
}
