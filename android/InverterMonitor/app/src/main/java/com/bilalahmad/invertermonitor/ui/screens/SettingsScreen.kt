package com.bilalahmad.invertermonitor.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.viewmodels.AuthViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.ui.components.InfoRow
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette
import java.text.SimpleDateFormat
import java.util.Locale

@Composable
fun SettingsScreen(
    authVM: AuthViewModel,
    liveVM: LiveDashboardViewModel,
    onSignOutCleanup: () -> Unit = {},
) {
    val serverURL by authVM.settings.serverURL.collectAsStateWithLifecycle()
    val connection by liveVM.connection.collectAsStateWithLifecycle()
    val lastUpdate by liveVM.lastUpdate.collectAsStateWithLifecycle()
    val readingStats by liveVM.readingStats.collectAsStateWithLifecycle()

    var showEditor by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Palette.BackgroundGradient)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            "Settings",
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            modifier = Modifier.padding(top = 24.dp, bottom = 8.dp),
        )

        SectionCard(title = "SERVER") {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Filled.Storage, contentDescription = null, tint = Palette.MutedText)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Server URL", color = Color.White, fontSize = 14.sp)
                    Text(serverURL, color = Palette.SubtleText, fontSize = 11.sp, maxLines = 1)
                }
                TextButton(onClick = { showEditor = true }) { Text("Edit") }
            }
        }

        SectionCard(title = "CONNECTION STATUS") {
            InfoRow("State", connection.label)
            lastUpdate?.let { date ->
                InfoRow("Last update", SimpleDateFormat("h:mm:ss a", Locale.getDefault()).format(date))
            }
            readingStats?.let { stats ->
                InfoRow("Total readings", stats.totalReadings.toString())
                stats.errorCount?.let { InfoRow("Errors", it.toString()) }
                InfoRow("Avg cycle", String.format(Locale.US, "%.0f ms", stats.avgDuration * 1000))
            }
        }

        SectionCard(title = "SESSION") {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.ExitToApp,
                    contentDescription = null,
                    tint = Color(0xFFFF6B6B),
                )
                Spacer(Modifier.width(12.dp))
                Text("Sign out", color = Color(0xFFFF6B6B), modifier = Modifier.weight(1f))
                TextButton(onClick = {
                    liveVM.resetSessionState()
                    onSignOutCleanup()
                    authVM.signOut()
                }) { Text("Sign out", color = Color(0xFFFF6B6B)) }
            }
        }

        SectionCard(title = "ABOUT") {
            InfoRow("Version", "1.0 · build 1")
            InfoRow("Deployment", "Android 9+ (API 28)")
        }

        Spacer(Modifier.height(40.dp))
    }

    if (showEditor) {
        ServerURLEditorSheet(
            initial = serverURL,
            onSave = { authVM.settings.setServerURL(it); showEditor = false },
            onDismiss = { showEditor = false },
        )
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column {
        Text(
            title,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            color = Palette.SubtleText,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 6.dp),
        )
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .card()
                .padding(12.dp),
            content = content,
        )
    }
}
