# Inverter Monitor · iOS

Native SwiftUI app that mirrors the Flask inverter web app 1:1. iPhone + iPad, iOS 17+.

## Open in Xcode

```bash
open ios/InverterMonitor/InverterMonitor.xcodeproj
```

Pick **InverterMonitor** scheme, target any iOS 17+ simulator or device, and run.

## Build from the command line

Device (no signing needed for validation):

```bash
xcodebuild \
  -project ios/InverterMonitor/InverterMonitor.xcodeproj \
  -target InverterMonitor \
  -sdk iphoneos \
  -configuration Debug \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  build
```

Simulator:

```bash
xcodebuild \
  -project ios/InverterMonitor/InverterMonitor.xcodeproj \
  -target InverterMonitor \
  -sdk iphonesimulator \
  -configuration Debug \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  build
```

Both configurations (Debug + Release, device + simulator) compile with zero errors and zero warnings.

## First-run configuration

1. Launch the app. You'll land on the **Sign in** screen.
2. Tap the server tile at the bottom and enter your Flask server URL
   (defaults to `http://192.168.18.130:5000`). Protocol is optional; `http://`
   is assumed when omitted.
3. Use the same `INVERTER_ADMIN_USERNAME` / `INVERTER_ADMIN_PASSWORD` pair that
   the Flask service uses.
4. Session cookies are handled automatically by `URLSession`.

## What's included

- **Live tab** — the Solar Flow dashboard translated to SwiftUI:
  - Mode pill (solid or dashed border when QMOD is unavailable), charge stage pill, grid pill.
  - Tappable diamond flow diagram with animated dashed flow lines (direction-aware for battery).
  - Power cards for Solar / Battery / Grid / Load, with EST badge when grid is estimated.
  - Today's summary strip (kWh totals, self-sufficiency, solar fraction).
  - System info grid (temperature, bus voltage, connection, reading cycle).
  - Live power chart (Apple Charts) with 5m/30m/2h/6h toggle and min/max envelope.
  - Tap any component to open a detail sheet with stats and (for load/battery)
    output + charger priority pickers with confirmation + toast feedback.
  - Refresh button triggers `/refresh-extras` to re-query QMOD/QPIWS/QPIRI on demand.
- **Reports tab** — Day / Month / Year / Outages / Raw segmented control:
  - Day: date nav, kWh summary, Apple Charts timeline, export menu (CSV/JSON
    at raw 3s, 1-min, 5-min) using the native share sheet.
  - Month: month picker, totals + stacked bar chart over the selected month.
  - Year: year picker, totals + monthly breakdown bars.
  - Outages: from/to picker, 7d/30d presets, count/downtime/availability KPIs, list.
  - Raw: paginated table with page-size toggle (10/25/50/100) and full paging controls.
- **Settings tab** — server URL editor, connection health check, connection status,
  total readings, error count, reading cycle, sign-out, about.

## Architecture

- `App/` — `@main` app, environment container wiring all services + ViewModels.
- `Models/` — decodable types mirroring the Flask JSON shapes (InverterStatus,
  InverterMetrics, SystemInfo, Summary/Stats, Readings, Config).
- `Services/`
  - `AppSettings` — `@Published` server URL persisted to UserDefaults.
  - `APIClient` — `URLSession` wrapper with cookie jar, CSRF scraping from
    `meta[name="csrf-token"]` or login form, JSON/form encoding, rate-limit
    handling. Writes include `X-CSRFToken` header.
  - `AuthService` — login/logout via Flask `POST /login` form, session
    verification via `/summary`.
  - `InverterService` — all read endpoints and file exports.
  - `CommandService` — `/refresh-extras`, `/set-output-priority`,
    `/set-charger-priority`, `/recompute-daily`.
- `ViewModels/` — MainActor ObservableObjects (AuthViewModel,
  LiveDashboardViewModel with polling loops, ReportsViewModel with per-tab state).
- `Views/`
  - `RootView` / `LoginView` / `MainTabView` / `SettingsView`
  - `Live/` — dashboard subviews (FlowDiagram, PowerCards, TodaySummary,
    SystemInfoGrid, LivePowerChart, ComponentDetailSheet + Load/Battery/Inverter sections).
  - `Reports/` — Day / Month / Year / Outages / Raw.
  - `Shared/` — `Palette`, `StatTile`, `InfoRow`, `StatusPill`.

## Real-time strategy

The web app uses Socket.IO; iOS polls instead:

- `/status` every 3 seconds while the Live tab is on screen (matches the
  Flask background reader cadence).
- `/stats` once a minute for the Today / reading-stats sections.
- `/recent-readings` every 3–10 seconds depending on the selected range.

Polling keeps the networking layer small and avoids maintaining a
WebSocket/Socket.IO dependency. If a session expires, the ViewModel surfaces
the offline state and the user is pushed back to the Login screen on the next
hard refresh.

## Regenerating the Xcode project

`InverterMonitor.xcodeproj` is generated from `ios/generate_project.rb` using
the `xcodeproj` Ruby gem (bundled with CocoaPods). After adding or removing
files, run:

```bash
bash ios/scripts/gen.sh
```

Source files live in `ios/InverterMonitor/InverterMonitor/{App,Models,Services,ViewModels,Views}/`.
The generator recurses into those folders, so dropping a new `.swift` file in
place and re-running is enough — you don't need to edit `project.pbxproj` by hand.
