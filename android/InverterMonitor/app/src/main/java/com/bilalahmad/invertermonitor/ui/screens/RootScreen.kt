package com.bilalahmad.invertermonitor.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.viewmodels.AuthState
import com.bilalahmad.invertermonitor.data.viewmodels.AuthViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.theme.Palette

@Composable
fun RootScreen(
    authVM: AuthViewModel,
    liveVM: LiveDashboardViewModel,
    reportsVM: ReportsViewModel,
) {
    val state by authVM.state.collectAsStateWithLifecycle()
    Box(Modifier.fillMaxSize().background(Palette.BackgroundGradient)) {
        when (state) {
            AuthState.Idle, AuthState.Checking ->
                CircularProgressIndicator(
                    color = Palette.Solar,
                    modifier = Modifier.align(Alignment.Center),
                )
            AuthState.SignedOut, AuthState.SigningIn -> LoginScreen(authVM)
            AuthState.SignedIn -> MainTabScreen(authVM, liveVM, reportsVM)
        }
    }
}
