package com.bilalahmad.invertermonitor

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.bilalahmad.invertermonitor.data.viewmodels.AuthViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.LiveDashboardViewModel
import com.bilalahmad.invertermonitor.data.viewmodels.ReportsViewModel
import com.bilalahmad.invertermonitor.ui.screens.RootScreen
import com.bilalahmad.invertermonitor.ui.theme.InverterMonitorTheme

class MainActivity : ComponentActivity() {
    private lateinit var authVM: AuthViewModel
    private lateinit var liveVM: LiveDashboardViewModel
    private lateinit var reportsVM: ReportsViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as InverterMonitorApp

        val factory = viewModelFactory {
            initializer { AuthViewModel(app.settings, app.auth) }
            initializer { LiveDashboardViewModel(app.inverter, app.commands) }
            initializer { ReportsViewModel(app.inverter) }
        }

        val provider = ViewModelProvider(this, factory)
        authVM = provider[AuthViewModel::class.java]
        liveVM = provider[LiveDashboardViewModel::class.java]
        reportsVM = provider[ReportsViewModel::class.java]

        // Session expired anywhere → sign out, reset live state, invalidate history cache.
        val expiredHandler: () -> Unit = {
            liveVM.resetSessionState()
            reportsVM.invalidateHistoryCache()
            authVM.signOut()
        }
        liveVM.onSessionExpired = expiredHandler
        reportsVM.onSessionExpired = expiredHandler
        liveVM.onNewFault = { app.notifier.postFault(it) }
        app.commands.onDidRecompute = { reportsVM.invalidateHistoryCache() }

        authVM.bootstrap()

        setContent {
            InverterMonitorTheme {
                Surface {
                    RootScreen(
                        authVM = authVM,
                        liveVM = liveVM,
                        reportsVM = reportsVM,
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        liveVM.start()
    }

    override fun onStop() {
        super.onStop()
        liveVM.stop()
    }
}
