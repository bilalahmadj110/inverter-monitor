package com.bilalahmad.invertermonitor

import android.app.Application
import com.bilalahmad.invertermonitor.data.services.ApiClient
import com.bilalahmad.invertermonitor.data.services.AppSettings
import com.bilalahmad.invertermonitor.data.services.AuthService
import com.bilalahmad.invertermonitor.data.services.CommandService
import com.bilalahmad.invertermonitor.data.services.InverterService
import com.bilalahmad.invertermonitor.data.services.NotificationCoordinator
import com.bilalahmad.invertermonitor.data.services.PersistentCookieJar

/**
 * Application-level DI container — mirrors iOS's `AppEnvironment`. Lives as long as
 * the process; ViewModels receive these services via a factory tied to this instance.
 */
class InverterMonitorApp : Application() {
    lateinit var settings: AppSettings
        private set
    lateinit var cookieJar: PersistentCookieJar
        private set
    lateinit var api: ApiClient
        private set
    lateinit var auth: AuthService
        private set
    lateinit var inverter: InverterService
        private set
    lateinit var commands: CommandService
        private set
    lateinit var notifier: NotificationCoordinator
        private set

    override fun onCreate() {
        super.onCreate()
        settings = AppSettings(this)
        cookieJar = PersistentCookieJar(this)
        api = ApiClient(settings, cookieJar)
        auth = AuthService(api)
        inverter = InverterService(api)
        commands = CommandService(api)
        notifier = NotificationCoordinator(this)
    }
}
