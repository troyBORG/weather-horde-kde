import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation
    Layout.minimumWidth: 260
    Layout.minimumHeight: 110
    toolTipMainText: statusTitle
    toolTipSubText: statusDetails
    property double lastStatusCheck: 0
    property double clockNow: Date.now()
    property var guardDetails: ({})
    property bool overrideSupported: false
    property string serviceVersion: "unknown (legacy controller)"
    property string applyBlocker: "Controller not verified"
    readonly property string applyEligibilityText: !online ? "Apply unavailable: controller disconnected" : !applySupported ? applyBlocker : selectedTarget === "all" ? "Apply blocked: select one monitor" : !imagePreviewReady ? "Apply blocked: no validated saved preview. Quarantined output cannot be applied." : previewTargets.indexOf(selectedTarget) < 0 ? "Apply blocked: saved preview does not match selected monitor" : "Ready: apply the saved image to " + selectedTarget + ". No Comfy startup or regeneration required."
    property bool applySupported: false
    property bool scheduledImagesSupported: false
    property string automationKind: "prompt_preview"
    property string automationTarget: "all"
    property string previewId: ""
    property var previewTargets: []
    property var restoreTargets: []
    readonly property string automationScopeText: automationKind === "image_wallpaper" ? "generate + apply · " + automationTarget : automationKind === "image_preview" ? "image previews only" : "prompt previews only"
    property int overrideServerSeconds: 0
    readonly property int overrideRemaining: Math.max(0, overrideServerSeconds - Math.floor(Math.max(0, clockNow-lastStatusCheck)/1000))
    readonly property bool overrideActive: online && overrideRemaining > 0

    readonly property bool statusStale: lastStatusCheck > 0 && clockNow - lastStatusCheck > 60000
    readonly property string effectiveGuard: statusStale ? "unknown" : guardState
    readonly property string automationSummary: !online ? "Automation: not verified" : (overrideActive ? "Automation paused · testing override" : "Automation " + (automationEnabled ? "on" : "off") + " · " + automationScopeText)
    readonly property string checkSummary: lastStatusCheck === 0 ? "Status not checked yet" : "Last check: " + new Date(lastStatusCheck).toLocaleTimeString() + (statusStale ? " · stale — refresh required" : "")
    readonly property string statusTitle: {
        if (controllerToken.length < 32) return "Not paired"
        if (!online) return "Disconnected"
        if (overrideActive) return "Testing override — " + overrideRemaining + "s"
        if (effectiveGuard === "game_active") return "Paused — game detected"
        if (effectiveGuard === "vr_active") return "Paused — VR detected"
        if (effectiveGuard === "gpu_busy") return "Paused — GPU busy"
        if (effectiveGuard === "insufficient_vram") return "Paused — low VRAM"
        if (effectiveGuard !== "safe") return "Monitoring unknown"
        if (controllerState === "queued") return "Queued — image preview"
        if (controllerState === "rendering") return "Rendering — image preview"
        if (controllerState === "rendering_guard_blocked") return "Guard blocked — job in flight"
        if (controllerState === "quarantined") return "Preview quarantined"
        if (controllerState === "blocked_preview_only" || !renderEnabled) return "Preview only"
        if (controllerState === "failed") return "Preview failed"
        if (!automationEnabled) return "Automation off"
        return "Idle — ready"
    }
    readonly property string statusReason: {
        let reason = ""
        if (controllerToken.length < 32) reason = connectionSummary + ". Manual pairing remains available."
        else if (!online) reason = "Cannot reach the authenticated controller. Activity is not verified."
        else if (overrideActive) reason = "Manual previews may bypass activity guards. Stutter / OOM risk accepted. Ownership, queue and VRAM checks still apply. Raw guard: " + guardState
        else if (statusStale) reason = "Status is stale; current activity is not verified."
        else if (effectiveGuard === "game_active") reason = "Game-like process detected by controller; new GPU previews are deferred."
        else if (effectiveGuard === "vr_active") reason = "VR process detected by controller; new GPU previews are deferred."
        else if (effectiveGuard === "gpu_busy") reason = "Sustained GPU load is above the safe threshold."
        else if (effectiveGuard === "insufficient_vram") reason = "Free VRAM is below the controller safety reserve."
        else if (effectiveGuard !== "safe") {
            const diagnostics = {
                graphical_owner_visibility: "Controller cannot verify the graphical owner; run it in your KDE session.",
                sampling_window: "Need two GPU samples 10–30 seconds apart; wait for the next monitor check.",
                unrecognized_gpu_client: "A GPU client is outside the reviewed desktop / owned-Comfy allowlist.",
                utilization_unavailable: "GPU utilization samples are unavailable.",
                active_client_counters_unavailable: "Active-job per-client engine counters are incomplete.",
                unexplained_gpu_load: "GPU load cannot be attributed exclusively to this job.",
                vram_unavailable: "Free VRAM is unavailable; testing override cannot bypass this.",
                collector_read_failed: "A process / GPU telemetry read failed; check controller diagnostics."
            }
            reason = diagnostics[guardDetails.reason] || "Activity / GPU telemetry is incomplete or unknown; rendering is blocked."
            if (guardDetails.reason) reason += " Check: " + guardDetails.reason
            if (guardDetails.sample_gap_seconds !== undefined) reason += " · sample gap " + guardDetails.sample_gap_seconds + "s"
        }
        else if (!renderEnabled) reason = "Image rendering is not configured; prompt previews only."
        else reason = "Guard reports safe. Generate now previews images; Apply changes one selected monitor. Automation: " + automationScopeText + "."
        if (controllerState === "rendering_guard_blocked") reason += " A job is still in flight; its output will be quarantined, not applied."
        if (controllerState === "quarantined") reason = "Previous render quarantined: " + (quarantineEvidence ? quarantineEvidence.decision + " / " + quarantineEvidence.reason + " at " + new Date(quarantineEvidence.at*1000).toLocaleTimeString() : "original reason unavailable in this controller revision") + ". Current guard: " + effectiveGuard + ". Safe now does not release old output; Generate a new preview. No wallpaper was applied by that render."
        return reason
    }
    readonly property string statusDetails: statusTitle + "\n" + connectionSummary + "\n" + statusReason + "\n" + automationSummary + "\nWallpaper changes: manual Apply / Restore, or explicitly enabled Auto\n" + checkSummary + "\nController: " + controllerState + " · guard: " + guardState + (guardDetails.free_mib !== undefined ? " · free VRAM: " + guardDetails.free_mib + " MiB" : "") + "\nActivity guards remain enforced unless testing override is explicitly confirmed."
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.clockNow = Date.now() }
    // Mutable for isolated Plasma harness; request() enforces literal loopback.
    property string controllerBase: "http://127.0.0.1:8734"
    // Token lives in this process only, never in Plasma configuration.
    property string controllerToken: ""
    property var pairingReader: null
    property bool autoTokenLoaded: false
    property bool manualPairing: false
    property int reconnectMinimumMs: 2000
    property int reconnectMaximumMs: 30000
    property int reconnectDelayMs: reconnectMinimumMs
    property int statusTimeoutMs: 5000
    property int statusPollMs: 30000
    readonly property string connectionSummary: online ? "Paired · local controller connected" :
        controllerToken.length >= 32 ? "Disconnected · local token found — retrying automatically" :
        pairingReader ? "Not paired · " + (pairingReader.diagnostic || "checking private local controller token") :
                        "Not paired · local helper unavailable; manual pairing available"
    Component.onCompleted: {
        // An optional component keeps manual pairing usable if a native plugin
        // cannot load after a Qt ABI upgrade. No eval or command execution.
        const component = Qt.createComponent("AutoPairing.qml")
        if (component.status === Component.Ready)
            pairingReader = component.createObject(root)
        reconnectTimer.start()
    }
    function pairManually(value) {
        manualPairing = true
        controllerToken = value.trim()
        refreshStatus()
    }
    function reconnectAutomatically() {
        manualPairing = false
        refreshStatus()
    }
    property string controllerState: "Not paired"
    property string guardState: "unknown"
    property string wallpaperGuardState: "unknown"
    property bool online: false
    property bool busy: false
    property var activeRequest: null
    property bool catchupEnabled: false
    property var refreshState: ({})
    readonly property string refreshSummary: {
        if (!online || statusStale) return "Refresh: disconnected / last known; no current success verified"
        if (!catchupEnabled) return "Catch-up disabled — interval policy unchanged"
        let pending = refreshState.pending || []
        let applied = (refreshState.last_success || {}).image_wallpaper || {}
        let history = Object.keys(applied).map(function(k) { return k + ": " + new Date(applied[k]*1000).toLocaleString() }).join(" · ")
        return "Refresh " + (pending.length ? "pending: " + pending.join(", ") : "not pending") +
            " · " + (refreshState.waiting_reason || "unknown") +
            " · settling " + (refreshState.settling_seconds || 0) + "s" +
            (refreshState.retry_seconds ? " · retry " + refreshState.retry_seconds + "s" : "") +
            (refreshState.action_required ? " · action required" : "") +
            "\nLast verified wallpaper change: " + (history || "none recorded (prompt/preview is not wallpaper)")
    }
    property bool automationEnabled: false
    property int intervalMinutes: 60
    readonly property var intervals: [30, 60, 120, 240, 480, 720, 1440]
    property var monitors: []
    property string selectedTarget: "all"
    property var candidates: []
    property int candidateIndex: 0
    property string locationLabel: "Suggested: 52742 — DeWitt, Iowa; confirm before use"
    property string displayNotice: "Live displays not yet detected"
    property string actionNotice: ""
    property string lastRenderMessage: ""
    property var quarantineEvidence: null
    property string comfySummary: "Comfy lifecycle not verified"
    property string imagePreviewSource: ""
    property bool imagePreviewReady: false
    property bool renderEnabled: false
    property string imagePreviewCaption: "No validated image preview yet"
    property string previewText: "No preview yet. No image rendered."

    property bool compositionSupported: false
    property string framingMode: "auto"
    property bool rotationSupported: false
    property var sceneOverrides: ({})
    property string sceneMonitor: ""
    readonly property var sceneKeys: ["rural","townpark","woodland","urban","river","random"]
    readonly property var sceneLabels: ["Rural / farmland", "Town park", "Woodland edge", "Small-town street", "Riverbank", "Random — new scene each generation"]
    property bool sceneSupported: false
    property bool modelSupported: false
    property string sceneKind: "rural"
    property string promptVersion: "not loaded"
    property string evidenceText: "No weather evidence yet"
    property string weatherSource: "Provider not verified"
    property string confirmedZip: ""
    property bool observationActive: false
    property var localModels: []
    property string selectedCheckpoint: ""
    property string modelNotice: ""
    function setObservation(fields) {
        request("PUT", "/v1/observation", fields, function(status) { root.acceptStatus(status) })
    }
    function acceptStatus(status) {
        online = true
        rotationSupported = !!status.capabilities && status.capabilities.scene_rotation === true
        sceneOverrides = status.scene_overrides || ({})
        sceneSupported = !!status.capabilities && status.capabilities.scene_controls === true
        modelSupported = !!status.capabilities && status.capabilities.model_selection === true
        sceneKind = status.scene_kind || "rural"
        compositionSupported = !!status.capabilities && status.capabilities.composition_controls === true
        framingMode = status.framing || "auto"
        promptVersion = status.prompt_version || "not loaded — owner rollout required"
        confirmedZip = status.location ? status.location.zip : ""
        observationActive = !!status.observation && status.observation.active === true
        weatherSource = status.observation ? status.observation.source : "Provider not verified"
        if (observationActive) weatherSource += " · observed " + new Date(status.observation.observation.observed_at*1000).toLocaleString() + " · expires " + new Date(status.observation.observation.expires_at*1000).toLocaleTimeString()
        localModels = status.models || []
        selectedCheckpoint = status.checkpoint || ""
        modelNotice = status.model_notice || "Owner rollout required"
        if (status.preview && status.preview.weather_evidence) evidenceText = JSON.stringify(status.preview.weather_evidence, null, 2)
        reconnectDelayMs = reconnectMinimumMs
        reconnectTimer.stop()
        lastStatusCheck = Date.now()
        clockNow = lastStatusCheck
        guardDetails = status.guard || {}
        quarantineEvidence = status.quarantine || null
        renderEnabled = status.render_enabled === true
        serviceVersion = status.service_version || "unknown (legacy controller)"
        applyBlocker = status.apply_blocker || "Running controller cannot apply wallpapers; owner rollout required"
        overrideSupported = status.api_version === 1 && !!status.capabilities && status.capabilities.testing_override === true
        overrideServerSeconds = status.testing_override && status.testing_override.active ? status.testing_override.remaining_seconds : 0
        applySupported = status.api_version === 1 && !!status.capabilities && status.capabilities.manual_apply === true
        scheduledImagesSupported = !!status.capabilities && status.capabilities.scheduled_images === true
        automationKind = status.automation_kind || "prompt_preview"
        automationTarget = status.automation_target || "all"
        restoreTargets = status.restore_available || []
        const latest = status.image_preview
        const image = selectedTarget !== "all" ? ((status.previews_by_target || {})[selectedTarget] || (latest && (latest.targets || []).indexOf(selectedTarget)>=0 ? latest : null)) : latest
        previewId = image && !image.quarantined ? image.id : ""
        previewTargets = image && !image.quarantined ? (image.targets || []) : []
        if (image && !image.quarantined && typeof image.thumbnail === "string" && image.thumbnail.indexOf("data:image/png;base64,") === 0) {
            imagePreviewSource = image.thumbnail
            imagePreviewCaption = "Validated preview · " + image.width + "×" + image.height + " · " + (image.targets || []).join(", ") + " — wallpaper untouched"
        }
        else { imagePreviewSource = ""; imagePreviewCaption = "No validated image preview yet" }
        const service = status.comfy_service
        comfySummary = service && service.managed ? "Comfy: " + service.state + " — " + service.reason + (service.owned ? " (app-owned)" : " (not stop-owned)") : "Comfy: external / lifecycle not enabled"
        const render = status.render_request
        if (render) {
            const message = render.state + ": " + render.reason + (render.prompt_id ? " · prompt " + render.prompt_id : " · no prompt ID submitted")
            if (message !== lastRenderMessage) { actionNotice = message; lastRenderMessage = message }
        }
        const applied = status.wallpaper_action
        if (image && applied && applied.verified && applied.state === "applied" && applied.preview_id === image.id)
            imagePreviewCaption = "Applied and read back on " + applied.target + " · " + image.width + "×" + image.height + " (last verified action)"
        if (status.last_error) actionNotice = status.last_error
        controllerState = status.state
        guardState = status.guard ? status.guard.decision : "unknown"
        wallpaperGuardState = status.wallpaper_guard || guardState
        catchupEnabled = status.catch_up_refresh === true
        refreshState = status.refresh || ({})
        automationEnabled = status.automation_enabled === true
        intervalMinutes = status.interval_minutes
        monitors = status.displays || []
        if (!monitors.some(function(m) { return m.id === sceneMonitor })) sceneMonitor = monitors.length ? monitors[0].id : ""
        if (selectedTarget !== "all" && !monitors.some(function(m) { return m.id === selectedTarget }))
            selectedTarget = "all"
        displayNotice = status.display_error || ""
        if (status.location)
            locationLabel = status.location.town + ", " + status.location.state + " · " + status.location.timezone
        if (status.preview) showPreview(status.preview)
    }
    function showPreview(result) {
        if (result.weather_evidence) evidenceText = JSON.stringify(result.weather_evidence, null, 2)
        if (result.target_scenes && result.target_scenes.length > 0) {
            previewText = result.target_scenes.map(function(entry) {
                const m = entry.target, s = entry.scene
                return m.id + ": " + m.width + "×" + m.height + " · Framing: " + s.composition.profile +
                    "\n" + s.positive + "\n\nNegative: " + s.negative
            }).join("\n\n") + "\n\nPrompt/geometry preview only — no image rendered."
            return
        }
        previewText = result.positive + "\n\nNegative: " + result.negative + "\n\n" +
            (result.targets || []).map(function(m) { return m.id + ": " + m.width + "×" + m.height }).join("\n") +
            "\n\nPrompt/geometry preview only — no image rendered."
    }
    function failRequest(message) {
        online = false
        controllerState = "Request failed / disconnected"
        guardState = "unknown"
        actionNotice = message
        reconnectTimer.restart()
        reconnectDelayMs = Math.min(reconnectMaximumMs, Math.max(reconnectMinimumMs, reconnectDelayMs * 2))
    }
    function request(method, path, body, onSuccess) {
        if (busy) return
        if (!/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(controllerBase)) { failRequest("Controller must be loopback-only"); return }
        if (controllerToken.length < 32) { failRequest("Pair with the local controller token first"); return }
        busy = true
        const xhr = new XMLHttpRequest()
        activeRequest = xhr
        requestTimeout.interval = path === "/v1/status" ? statusTimeoutMs : 45000
        xhr.open(method, controllerBase + path)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.setRequestHeader("Authorization", "Bearer " + controllerToken)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE || activeRequest !== xhr) return
            requestTimeout.stop()
            activeRequest = null
            busy = false
            let response
            try { response = JSON.parse(xhr.responseText) }
            catch (error) { failRequest("Controller offline or invalid JSON response"); return }
            if (xhr.status >= 200 && xhr.status < 300) {
                online = true
                onSuccess(response)
            } else if (xhr.status === 400) {
                online = true
                actionNotice = "Request refused: " + (response.error || "Controller rejected request")
            } else if (xhr.status === 401 || xhr.status === 403) {
                failRequest("Controller authentication rejected; reconnect / check owner pairing")
            } else failRequest(response.error || "Controller unavailable")
        }
        requestTimeout.start()
        xhr.send(body === undefined ? null : JSON.stringify(body))
    }
    function refreshStatus() {
        if (busy) return
        if (!manualPairing && pairingReader) {
            const token = pairingReader.readToken()
            if (token.length >= 32) { controllerToken = token; autoTokenLoaded = true }
            else if (autoTokenLoaded) controllerToken = ""
        }
        if (controllerToken.length < 32) {
            online = false
            reconnectTimer.restart()
            reconnectDelayMs = Math.min(reconnectMaximumMs, Math.max(reconnectMinimumMs, reconnectDelayMs * 2))
            return
        }
        request("GET", "/v1/status", undefined, acceptStatus)
    }
    function currentTarget() { return selectedTarget }
    function preview() {
        request("POST", "/v1/preview", {"target": currentTarget()}, function(result) {
            controllerState = result.state
            showPreview(result)
            actionNotice = "Preview ready — wallpaper untouched"
        })
    }
    function lookup(zip) {
        candidates = []
        request("POST", "/v1/location/lookup", {"zip": zip}, function(result) {
            candidates = result.candidates || []
            candidateIndex = 0
            actionNotice = "Review coordinates and timezone, then confirm"
        })
    }
    function confirmLocation() {
        const candidate = candidates[candidateIndex]
        if (!candidate) return
        request("PUT", "/v1/settings", {"location_confirmation": candidate.confirmation_id}, function(result) {
            acceptStatus(result)
            candidates = []
            actionNotice = "Location confirmed"
        })
    }
    function saveSettings(body) {
        request("PUT", "/v1/settings", body, function(status) {
            acceptStatus(status)
            actionNotice = "Saved — automation: " + automationScopeText + (automationEnabled ? " · ON" : " · OFF")
        })
    }
    function setTestingOverride(enabled) {
        if (!overrideSupported) { actionNotice = "Running controller lacks override capability; owner rollout required"; return }
        request("PUT", "/v1/testing-override", {enabled: enabled, confirmation: enabled ? "I accept stutter and OOM risk" : ""}, function(status) {
            acceptStatus(status)
            actionNotice = enabled ? "Testing override enabled for 10 minutes. Manual previews only; wallpaper untouched." : "Testing override OFF. In-flight output will be quarantined."
        })
    }
    function applyPreview() {
        actionNotice = "Applying selected preview — waiting for verified monitor readback"
        request("POST", "/v1/apply", {target: currentTarget(), preview_id: previewId, confirmation: "Apply this validated preview"}, function(result) {
            controllerState = result.state
            actionNotice = "Applied and read back on " + result.target
            refreshStatus()
        })
    }
    function restoreWallpaper() {
        request("POST", "/v1/restore", {target: currentTarget(), confirmation: "Restore previous wallpaper"}, function(result) {
            controllerState = result.state
            actionNotice = "Restored and read back on " + result.target
            refreshStatus()
        })
    }
    function generate() {
        actionNotice = "Checking eligibility — no Comfy job submitted yet"
        request("POST", "/v1/render", {"target": currentTarget(), "force": true}, function(result) {
            controllerState = result.state
            actionNotice = result.state + ": " + result.reason
            refreshStatus()
        })
    }

    Timer {
        id: requestTimeout
        interval: 45000
        onTriggered: {
            const xhr = activeRequest
            activeRequest = null
            if (xhr) xhr.abort()
            busy = false
            failRequest("Controller request timed out; refresh to reconcile saved settings")
        }
    }
    Timer { id: reconnectTimer; interval: root.reconnectDelayMs; onTriggered: root.refreshStatus() }
    Timer { interval: ["queued", "rendering", "rendering_guard_blocked"].indexOf(root.controllerState) >= 0 ? 2000 : root.statusPollMs; running: root.online; repeat: true; onTriggered: root.refreshStatus() }

    compactRepresentation: ToolButton {
        objectName: "compactLauncher"
        implicitWidth: 300
        implicitHeight: 130
        contentItem: ColumnLayout {
            spacing: 2
            Label { objectName: "compactStatusTitle"; text: root.statusTitle; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: root.automationSummary; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pointSize: 8 }
            Label { objectName: "compactReason"; text: root.statusReason; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; font.pointSize: 8 }
            Label { text: "Click for controls"; font.pointSize: 8 }
        }
        onClicked: root.expanded = !root.expanded
        ToolTip.visible: hovered
        ToolTip.text: root.statusDetails
    }
    fullRepresentation: ScrollView {
        id: fullView
        implicitWidth: 440
        implicitHeight: 700
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: fullView.availableWidth
            spacing: 10
            Label { text: root.applySupported ? "Weather Horde · Manual apply" : "Weather Horde · Preview only"; font.bold: true; font.pointSize: 14 }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap
                objectName: "rendererSummary"
                text: root.applySupported ? "Generate a preview, inspect it, select one matching monitor, then click Apply. Optional Auto generate + apply is a separate opt-in mode." : !root.online ? "Image rendering configuration not verified — controller disconnected. Wallpaper application remains locked off." : root.renderEnabled ? "Manual image previews enabled; wallpaper application remains locked off." : "Image rendering is not configured. Wallpaper application remains locked off."
            }
            Label { objectName: "expandedStatusTitle"; text: root.statusTitle; font.bold: true; font.pointSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { objectName: "connectionSummary"; text: root.connectionSummary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: root.statusReason; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: root.automationSummary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: "Controller: " + root.serviceVersion; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { objectName: "comfyServiceStatus"; text: root.comfySummary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { objectName: "renderActionNotice"; text: root.actionNotice; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: root.checkSummary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: "Activity guards remain enforced unless testing override is explicitly confirmed."; Layout.fillWidth: true; wrapMode: Text.Wrap }
            GroupBox {
                title: "Temporary testing override"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    CheckBox {
                        id: riskConfirmation
                        objectName: "testingOverrideRisk"
                        text: "I accept stutter and OOM risk"
                        Layout.fillWidth: true
                        enabled: !root.overrideActive && !root.busy
                    }
                    Switch {
                        objectName: "testingOverrideToggle"
                        text: root.overrideActive ? "Testing override ON" : "Testing override OFF"
                        checked: root.overrideActive
                        enabled: root.online && root.overrideSupported && !root.busy && (root.overrideActive || riskConfirmation.checked)
                        onClicked: {
                            const desired = checked
                            checked = Qt.binding(function() { return root.overrideActive })
                            root.setTestingOverride(desired)
                            riskConfirmation.checked = false
                        }
                    }
                    Label {
                        objectName: "testingOverrideCountdown"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: !root.overrideSupported ? (root.online ? "Connected to controller " + root.serviceVersion + ". Override unsupported: run owner rollout, not Pair. Checkbox acknowledges risk only." : "Connect to verify override support.") : root.overrideActive ? root.overrideRemaining + "s remaining · automation paused · manual image previews only" : "OFF · expires after 10 minutes or controller restart. No wallpaper changes."
                    }
                }
            }
            Button { text: "Reconnect automatically"; enabled: !root.busy; onClicked: root.reconnectAutomatically() }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: pairingToken
                    Layout.fillWidth: true
                    placeholderText: "Manual pairing fallback (session only)"
                    echoMode: TextInput.Password
                    onAccepted: { root.pairManually(text); text = "" }
                }
                Button {
                    text: "Pair"; enabled: !root.busy
                    onClicked: { root.pairManually(pairingToken.text); pairingToken.text = "" }
                }
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap
                text: "Guard: " + root.guardState + " · " + root.controllerState
                font.bold: true
            }
            BusyIndicator { running: root.busy; visible: running; Layout.preferredHeight: 28 }
            GroupBox {
                title: "Automation — " + root.automationScopeText
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    Switch {
                        text: "Automation"; checked: root.automationEnabled
                        enabled: root.online && !root.busy && !root.overrideActive
                        onClicked: {
                            const desired = checked
                            checked = Qt.binding(function() { return root.automationEnabled })
                            root.saveSettings({"automation_enabled": desired})
                        }
                    }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["Prompt previews only", "Generate image previews (never apply)", "Auto: generate + apply wallpapers"]
                        currentIndex: root.automationKind === "image_wallpaper" ? 2 : root.automationKind === "image_preview" ? 1 : 0
                        enabled: root.online && root.scheduledImagesSupported && !root.busy && !root.overrideActive
                        onActivated: root.saveSettings({automation_kind: currentIndex === 2 ? "image_wallpaper" : currentIndex === 1 ? "image_preview" : "prompt_preview"})
                    }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["Auto target: all active monitors"].concat(root.monitors.map(function(m) { return "Auto target: " + m.id }))
                        currentIndex: root.automationTarget === "all" ? 0 : root.monitors.findIndex(function(m) { return m.id === root.automationTarget }) + 1
                        enabled: root.online && !root.busy
                        onActivated: root.saveSettings({automation_target: currentIndex === 0 ? "all" : root.monitors[currentIndex-1].id})
                    }
                    Label { text: "Auto generate + apply changes the chosen target(s) at the interval only while safe. Games/VR defer background work; testing overrides never authorize Auto. OFF until explicitly enabled."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Switch {
                        objectName: "catchupRefreshToggle"
                        text: "Catch up overdue after unlock / gaming; pause while locked"
                        checked: root.catchupEnabled
                        enabled: root.online && !root.busy
                        onClicked: {
                            const desired = checked
                            checked = Qt.binding(function() { return root.catchupEnabled })
                            root.saveSettings({catch_up_refresh: desired})
                        }
                    }
                    Label { objectName: "refreshStatus"; text: root.refreshSummary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { text: "Catch-up waits for 60 seconds of continuously safe observations. It preserves Auto, mode, target and interval; enabling catch-up does not enable Auto."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { text: "Interval" }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["30 minutes", "1 hour", "2 hours", "4 hours", "8 hours", "12 hours", "Daily"]
                        currentIndex: root.intervals.indexOf(root.intervalMinutes)
                        enabled: root.online && !root.busy
                        onActivated: {
                            const minutes = root.intervals[currentIndex]
                            currentIndex = Qt.binding(function() { return root.intervals.indexOf(root.intervalMinutes) })
                            root.saveSettings({"interval_minutes": minutes})
                        }
                    }
                }
            }
            GroupBox {
                title: "Location"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: root.locationLabel; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    RowLayout {
                        TextField {
                            id: zipCode; text: "52742"; placeholderText: "ZIP code"; maximumLength: 5
                            inputMethodHints: Qt.ImhDigitsOnly; Layout.fillWidth: true
                            validator: RegularExpressionValidator { regularExpression: /[0-9]{5}/ }
                            onTextEdited: root.candidates = []
                        }
                        Button { text: "Look up"; enabled: root.online && !root.busy && zipCode.acceptableInput; onClicked: root.lookup(zipCode.text) }
                    }
                    ComboBox {
                        Layout.fillWidth: true; visible: root.candidates.length > 0
                        model: root.candidates.map(function(c) { return c.town + ", " + c.state + " · " + c.latitude + ", " + c.longitude + " · " + c.timezone })
                        currentIndex: root.candidateIndex
                        onActivated: root.candidateIndex = currentIndex
                    }
                    Button { text: "Use this location"; enabled: root.candidates.length > 0 && !root.busy; onClicked: root.confirmLocation() }
                }
            }
            GroupBox {
                title: "Scene / weather / local model"
                objectName: "sceneControlsGroup"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: "Prompt logic: " + root.promptVersion; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { text: "Weather-inspired regional scenes, not exact landmark reconstruction"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    ComboBox {
                        objectName: "sceneSelector"; Layout.fillWidth: true
                        model: root.rotationSupported ? root.sceneLabels : root.sceneLabels.slice(0,4)
                        currentIndex: root.sceneKeys.indexOf(root.sceneKind)
                        enabled: root.online && root.sceneSupported && !root.busy
                        onActivated: root.saveSettings({scene_kind:root.sceneKeys[currentIndex]})
                    }
                    Label { text: "Per-monitor scene" }
                    ComboBox {
                        objectName: "sceneMonitorSelector"; Layout.fillWidth: true
                        model: root.monitors.map(function(m) { return m.id })
                        currentIndex: root.monitors.findIndex(function(m) { return m.id === root.sceneMonitor })
                        enabled: root.online && root.rotationSupported && !root.busy
                        onActivated: root.sceneMonitor = root.monitors[currentIndex].id
                    }
                    ComboBox {
                        objectName: "monitorSceneSelector"; Layout.fillWidth: true
                        model: ["Inherit global scene"].concat(root.sceneLabels)
                        currentIndex: root.sceneOverrides[root.sceneMonitor] ? root.sceneKeys.indexOf(root.sceneOverrides[root.sceneMonitor])+1 : 0
                        enabled: root.online && root.rotationSupported && !root.busy && root.sceneMonitor.length > 0
                        onActivated: {
                            const overrides = Object.assign({}, root.sceneOverrides)
                            if (currentIndex === 0) delete overrides[root.sceneMonitor]
                            else overrides[root.sceneMonitor] = root.sceneKeys[currentIndex-1]
                            root.saveSettings({scene_overrides:overrides})
                        }
                    }
                    Label {
                        text: root.rotationSupported ? "Random chooses per monitor when generation starts, avoiding its last scene. Status checks never rotate it. Before the first render, prompt preview is illustrative. To change wallpapers automatically, select Auto generate + apply and enable automation above; GPU/game/VR safeguards still apply." : "Random and per-monitor scenes require owner controller rollout."
                        wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Label { text: "Framing" }
                    ComboBox {
                        objectName: "framingSelector"; Layout.fillWidth: true
                        model: ["Auto — portrait streets", "Natural — no framing guidance", "Widget-aware — portrait only"]
                        currentIndex: ["auto","natural","desktop_portrait"].indexOf(root.framingMode)
                        enabled: root.online && root.compositionSupported && !root.busy
                        onActivated: root.saveSettings({framing:["auto","natural","desktop_portrait"][currentIndex]})
                    }
                    Label {
                        text: root.compositionSupported ? "Auto raises portrait street detail above lower widgets. Landscape unchanged. Prompt guidance, not exact placement; widgets stay put." : "Framing requires owner controller rollout."
                        wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Label { text: root.weatherSource; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { text: "Manual observation: enter current conditions at the confirmed ZIP. Expires automatically; never inferred from an old photograph."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    ComboBox { id: observationCondition; Layout.fillWidth: true; currentIndex: 2; model: ["Clear", "Partly cloudy", "Overcast", "Fog", "Drizzle", "Rain", "Snowfall", "Thunderstorm"] }
                    RowLayout {
                        Label { text: "Temperature °F" }
                        SpinBox { id: observationTemp; from: -130; to: 140; value: 50; editable: true }
                    }
                    RowLayout {
                        Label { text: "Cloud %" }
                        SpinBox { id: observationCloud; from: 0; to: 100; value: 100; editable: true }
                    }
                    RowLayout {
                        Label { text: "Precipitation mm" }
                        TextField { id: observationRain; text: "0"; Layout.fillWidth: true; validator: DoubleValidator { bottom: 0; top: 300; locale: "C" } }
                    }
                    RowLayout {
                        Label { text: "Observed minutes ago" }
                        SpinBox { id: observationAge; from: 0; to: 30; value: 0 }
                    }
                    RowLayout {
                        Label { text: "Expires after minutes" }
                        SpinBox { id: observationTtl; from: 1; to: 60; value: 15 }
                    }
                    Button {
                        objectName: "observationEnable"; text: "Use this dated observation"
                        enabled: root.online && root.sceneSupported && !root.busy && root.confirmedZip.length === 5 && observationRain.acceptableInput
                        onClicked: root.setObservation({observed_at:Date.now()/1000-observationAge.value*60,ttl_minutes:observationTtl.value,temperature_f:observationTemp.value,cloud_cover_percent:observationCloud.value,precipitation_mm:Number(observationRain.text),weather_code:[0,2,3,45,51,61,71,95][observationCondition.currentIndex],location_zip:root.confirmedZip})
                    }
                    Button { text: "Revert to automatic weather"; enabled: root.online && root.sceneSupported && !root.busy; onClicked: root.setObservation({enabled:false}) }
                    Button { text: "Discover local Comfy models"; enabled: root.online && root.modelSupported && !root.busy; onClicked: root.request("POST","/v1/models/refresh",{},function(status){root.acceptStatus(status)}) }
                    ComboBox {
                        objectName: "modelSelector"; Layout.fillWidth: true
                        model: root.localModels.map(function(m){return m.id + " · " + m.architecture + " · " + m.native_resolution + " native · ≥" + m.min_free_mib + " MiB free"})
                        currentIndex: root.localModels.findIndex(function(m){return m.id===root.selectedCheckpoint})
                        enabled: root.online && root.modelSupported && !root.busy && root.localModels.length>0
                        onActivated: root.saveSettings({checkpoint:root.localModels[currentIndex].id})
                    }
                    Label { text: "Selected: " + root.selectedCheckpoint + "\n" + root.modelNotice + "\nTraining resolution is not output resolution. Bounded exact-aspect generation → 2× upscaler → native-size Lanczos; does not guarantee fine detail."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    TextField { id: comparisonSeed; placeholderText: "Same-seed comparison (0–4294967295)"; Layout.fillWidth: true; validator: RegularExpressionValidator { regularExpression: /[0-9]{1,10}/ } }
                    Button { text: "Set comparison seed"; enabled: root.online && root.modelSupported && !root.busy && comparisonSeed.acceptableInput; onClicked: root.saveSettings({comparison_seed:Number(comparisonSeed.text)}) }
                    Button { text: "Use random seeds"; enabled: root.online && root.modelSupported && !root.busy; onClicked: root.saveSettings({comparison_seed:null}) }
                    Label { text: "Compare manually, one model and one monitor at a time. Same seed does not guarantee comparable composition across architectures. GPU/game/VR guards still apply."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    TextArea { Layout.fillWidth: true; Layout.preferredHeight: 120; text: root.evidenceText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap }
                }
            }
            GroupBox {
                title: "Monitor / regeneration"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: root.displayNotice; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["All active monitors"].concat(root.monitors.map(function(m) { return m.id + " — " + m.width + "×" + m.height + " " + m.orientation }))
                        currentIndex: root.selectedTarget === "all" ? 0 : root.monitors.findIndex(function(m) { return m.id === root.selectedTarget }) + 1
                        onActivated: { root.selectedTarget = currentIndex === 0 ? "all" : root.monitors[currentIndex-1].id; root.refreshStatus() }
                    }
                    RowLayout {
                        Button { text: "Preview prompt"; enabled: root.online && !root.busy; onClicked: root.preview() }
                        Button {
                            text: "Generate now"; enabled: root.online && !root.busy
                            ToolTip.visible: hovered
                            ToolTip.text: "Normally deferred during games, VR, or unsafe GPU use. Confirmed testing override bypasses activity only, never ownership / queue / VRAM checks."
                            onClicked: root.generate()
                        }
                    }
                    Button {
                        objectName: "applyPreviewButton"
                        text: "Apply validated preview to " + (root.selectedTarget === "all" ? "selected monitor" : root.selectedTarget)
                        enabled: root.online && !root.busy && root.applySupported && root.imagePreviewReady && root.previewTargets.indexOf(root.selectedTarget) >= 0
                        onClicked: root.applyPreview()
                    }
                    Button {
                        text: "Restore previous wallpaper"
                        enabled: root.online && !root.busy && root.applySupported && root.restoreTargets.indexOf(root.selectedTarget) >= 0
                        onClicked: root.restoreWallpaper()
                    }
                    Label { objectName: "applyEligibility"; text: root.applyEligibilityText; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Label { objectName: "monitorActionNotice"; text: root.actionNotice; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }
            Image {
                Layout.fillWidth: true; Layout.preferredHeight: 240
                visible: root.imagePreviewSource.length > 0
                source: root.imagePreviewSource
                fillMode: Image.PreserveAspectFit
                cache: false
                onStatusChanged: root.imagePreviewReady = status === Image.Ready
            }
            Label { text: root.imagePreviewCaption; Layout.fillWidth: true; wrapMode: Text.Wrap }
            TextArea {
                Layout.fillWidth: true; Layout.preferredHeight: 190
                text: root.previewText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
            }
            Button { text: "Refresh status"; enabled: !root.busy; onClicked: root.refreshStatus() }
        }
    }
}
