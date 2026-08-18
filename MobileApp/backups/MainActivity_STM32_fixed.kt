@file:Suppress(
    "DEPRECATION",
    "MissingPermission",
    "SpellCheckingInspection"
)

package com.example.grapplercontrol

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import kotlin.math.cos
import kotlin.math.sin

private val Bg = Color(0xFF050814)
private val Card = Color(0xFF101827)
private val CardDark = Color(0xFF0B1220)
private val Border = Color(0xFF223044)
private val TextMain = Color(0xFFF8FAFC)
private val TextMuted = Color(0xFF94A3B8)
private val Blue = Color(0xFF2563EB)
private val Red = Color(0xFFDC2626)
private val Amber = Color(0xFFF59E0B)
private val Green = Color(0xFF22C55E)
private val Slate = Color(0xFF334155)
private val Disabled = Color(0xFF1F2937)

private const val SERVO1_HOME = 175f
private const val SERVO2_HOME = 5f
private const val SERVO1_GRIP = 5f
private const val SERVO2_GRIP = 175f
private const val COMMAND_COOLDOWN_MS = 120L

class MainActivity : ComponentActivity() {
    private val sppUuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

    private var socket: BluetoothSocket? = null
    private var output: OutputStream? = null
    private var input: InputStream? = null
    private var readerThread: Thread? = null
    private var readerRunning = false

    private var onBluetoothMessage: ((String) -> Unit)? = null
    private var onBluetoothDisconnected: (() -> Unit)? = null
    private var onVoiceResult: ((String) -> Unit)? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {}

    private val voiceLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            if (spoken.isNotEmpty()) onVoiceResult?.invoke(spoken)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestBluetoothPermissions()

        setContent {
            GrapplerTheme {
                GrapplerScreen(
                    getDevices = { getPairedDevices() },
                    connectDevice = { connectToDevice(it) },
                    disconnect = { disconnect() },
                    sendCommand = { sendFramedCommand(it) },
                    startVoiceRecognition = { startVoiceRecognition() },
                    setBluetoothListener = { onBluetoothMessage = it },
                    setDisconnectListener = { onBluetoothDisconnected = it },
                    setVoiceListener = { onVoiceResult = it }
                )
            }
        }
    }

    private fun requestBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissionLauncher.launch(
                arrayOf(
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.BLUETOOTH_SCAN
                )
            )
        }
    }

    private fun hasBluetoothConnectPermission(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_CONNECT
            ) == PackageManager.PERMISSION_GRANTED
    }

    private fun startVoiceRecognition() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "bs-BA")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Reci komandu: uhvati, pusti, home, otvori, zategni, ping...")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }

        try {
            voiceLauncher.launch(intent)
        } catch (_: Exception) {
            onVoiceResult?.invoke("VOICE_ERROR")
        }
    }

    private fun getPairedDevices(): List<BluetoothDevice> {
        if (!hasBluetoothConnectPermission()) return emptyList()

        val adapter = BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        return adapter.bondedDevices.toList().sortedWith(
            compareByDescending<BluetoothDevice> {
                val name = it.name ?: ""
                name.contains("HC", ignoreCase = true) ||
                    name.contains("BT", ignoreCase = true)
            }.thenBy { it.name ?: it.address }
        )
    }

    private suspend fun connectToDevice(device: BluetoothDevice): Boolean = withContext(Dispatchers.IO) {
        if (!hasBluetoothConnectPermission()) return@withContext false

        try {
            disconnect()
            BluetoothAdapter.getDefaultAdapter()?.cancelDiscovery()

            val s = device.createRfcommSocketToServiceRecord(sppUuid)
            s.connect()

            socket = s
            output = s.outputStream
            input = s.inputStream

            startReaderThread()
            true
        } catch (_: Exception) {
            disconnect()
            false
        }
    }

    private fun sendFramedCommand(command: String): Boolean {
        return try {
            val s = socket ?: return false
            val out = output ?: return false
            if (!s.isConnected) return false

            val cleaned = command.trim()
                .removePrefix("<")
                .removeSuffix(">")

            if (cleaned.isEmpty()) return false

            val frame = "<$cleaned>"
            out.write(frame.toByteArray(Charsets.US_ASCII))
            out.flush()
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun startReaderThread() {
        readerRunning = true

        readerThread = Thread {
            val buffer = StringBuilder()

            try {
                while (readerRunning && socket?.isConnected == true) {
                    val b = input?.read() ?: break

                    if (b == '\n'.code) {
                        val line = buffer.toString().trim()
                        buffer.clear()
                        if (line.isNotEmpty()) {
                            runOnUiThread { onBluetoothMessage?.invoke(line) }
                        }
                    } else if (b != '\r'.code) {
                        buffer.append(b.toChar())
                    }
                }
            } catch (_: Exception) {
            } finally {
                runOnUiThread { onBluetoothDisconnected?.invoke() }
            }
        }

        readerThread?.start()
    }

    private fun disconnect() {
        readerRunning = false

        try { input?.close() } catch (_: Exception) {}
        try { output?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}

        input = null
        output = null
        socket = null
        readerThread = null
    }

    override fun onDestroy() {
        disconnect()
        super.onDestroy()
    }
}

@Composable
fun GrapplerScreen(
    getDevices: () -> List<BluetoothDevice>,
    connectDevice: suspend (BluetoothDevice) -> Boolean,
    disconnect: () -> Unit,
    sendCommand: (String) -> Boolean,
    startVoiceRecognition: () -> Unit,
    setBluetoothListener: (((String) -> Unit)?) -> Unit,
    setDisconnectListener: (() -> Unit) -> Unit,
    setVoiceListener: (((String) -> Unit)?) -> Unit
) {
    val scope = rememberCoroutineScope()
    val scroll = rememberScrollState()
    val haptic = LocalHapticFeedback.current

    val logs = remember { mutableStateListOf<String>() }

    var devices by remember { mutableStateOf<List<BluetoothDevice>>(emptyList()) }
    var selectedDevice by remember { mutableStateOf<BluetoothDevice?>(null) }

    var connected by remember { mutableStateOf(false) }
    var connecting by remember { mutableStateOf(false) }

    var servo1 by remember { mutableFloatStateOf(SERVO1_HOME) }
    var servo2 by remember { mutableFloatStateOf(SERVO2_HOME) }
    var grip by remember { mutableStateOf(0) }

    var lastCommand by remember { mutableStateOf("Nema") }
    var lastAck by remember { mutableStateOf("—") }
    var lastRx by remember { mutableStateOf("—") }
    var lastVoice by remember { mutableStateOf("—") }

    var liveCalibration by remember { mutableStateOf(false) }
    var pendingVoiceCommand by remember { mutableStateOf<String?>(null) }
    var pendingVoiceLabel by remember { mutableStateOf<String?>(null) }
    var assistantText by remember { mutableStateOf("Voice Assistant spreman.") }

    var lastSendAt by remember { mutableLongStateOf(0L) }

    fun timeNow(): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

    fun log(level: String, message: String) {
        logs.add("[${timeNow()}] [$level] $message")
        while (logs.size > 160) logs.removeAt(0)
    }

    fun updateGripFromServos() {
        grip = gripIntensity(servo1, servo2)
    }

    fun parseState(line: String) {
        try {
            val payload = line.substringAfter("STATE:", "")
            val parts = payload.split(";")
                .mapNotNull {
                    val pair = it.split("=", limit = 2)
                    if (pair.size == 2) pair[0].trim() to pair[1].trim() else null
                }
                .toMap()

            parts["S1"]?.toFloatOrNull()?.let { servo1 = it.coerceIn(0f, 180f) }
            parts["S2"]?.toFloatOrNull()?.let { servo2 = it.coerceIn(0f, 180f) }
            parts["GRIP"]?.toIntOrNull()?.let { grip = it.coerceIn(0, 100) } ?: updateGripFromServos()
        } catch (_: Exception) {
            log("WARN", "STATE parsiranje nije uspjelo")
        }
    }

    fun send(command: String, label: String, urgent: Boolean = false): Boolean {
        if (!connected) {
            log("WARN", "Sistem nije povezan")
            return false
        }

        val t = SystemClock.elapsedRealtime()
        if (!urgent && t - lastSendAt < COMMAND_COOLDOWN_MS) {
            log("WAIT", "Komanda je prebrza")
            return false
        }

        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        lastSendAt = t

        val ok = sendCommand(command)

        if (ok) {
            lastCommand = label
            log("TX", "<$command> $label")
        } else {
            log("ERROR", "Komanda nije poslana")
        }

        return ok
    }

    fun setPreviewForCommand(command: String) {
        when (command) {
            "g", "c" -> {
                servo1 = SERVO1_GRIP
                servo2 = SERVO2_GRIP
                updateGripFromServos()
            }
            "f", "h", "o" -> {
                servo1 = SERVO1_HOME
                servo2 = SERVO2_HOME
                updateGripFromServos()
            }
        }
    }

    fun sendAndPreview(command: String, label: String, urgent: Boolean = false) {
        if (send(command, label, urgent)) {
            setPreviewForCommand(command)
        }
    }

    fun interpretVoice(spokenRaw: String) {
        val spoken = spokenRaw.lowercase(Locale.getDefault())
        lastVoice = spokenRaw
        log("VOICE", spokenRaw)

        fun propose(cmd: String, label: String) {
            pendingVoiceCommand = cmd
            pendingVoiceLabel = label
            assistantText = "Predložena komanda: $label. Klikni POTVRDI za slanje."
            log("ASSIST", "Predloženo: <$cmd> $label")
        }

        when {
            spokenRaw == "VOICE_ERROR" -> {
                assistantText = "Telefon ne može otvoriti voice recognition."
                log("ERROR", assistantText)
            }

            "uhvati" in spoken || "grab" in spoken || "zatvori" in spoken || "stisni" in spoken -> {
                propose("g", "UHVATI")
            }

            "zategni" in spoken || "close" in spoken -> {
                propose("c", "ZATEGNI")
            }

            "pusti" in spoken || "stop" in spoken || "prekid" in spoken || "emergency" in spoken -> {
                propose("f", "E-STOP / PUSTI")
            }

            "home" in spoken || "počet" in spoken || "pocet" in spoken -> {
                propose("h", "HOME")
            }

            "otvori" in spoken || "open" in spoken -> {
                propose("o", "OTVORI")
            }

            ("test" in spoken && ("jedan" in spoken || "1" in spoken || "servo 1" in spoken)) -> {
                propose("1", "TEST S1")
            }

            ("test" in spoken && ("dva" in spoken || "2" in spoken || "servo 2" in spoken)) -> {
                propose("2", "TEST S2")
            }

            "ping" in spoken || "provjeri" in spoken || "stanje" in spoken -> {
                propose("?", "PING / STATE")
            }

            else -> {
                pendingVoiceCommand = null
                pendingVoiceLabel = null
                assistantText = "Nisam siguran šta znači: '$spokenRaw'. Probaj: uhvati, pusti, home, otvori, zategni, ping."
                log("ASSIST", "Neprepoznata voice komanda")
            }
        }
    }

    LaunchedEffect(Unit) {
        devices = getDevices()
        log("INFO", "Aplikacija pokrenuta. Protokol: <g>, <h>, <A090>...")

        setBluetoothListener { line ->
            lastRx = line
            log("RX", line)

            when {
                line.startsWith("ACK:") -> {
                    lastAck = line.removePrefix("ACK:").trim()
                }
                line.startsWith("STATE:") -> {
                    parseState(line)
                }
                line.startsWith("ERR:") -> {
                    lastAck = "ERR"
                }
            }
        }

        setDisconnectListener {
            if (connected) {
                connected = false
                connecting = false
                log("WARN", "Bluetooth veza je prekinuta")
            }
        }

        setVoiceListener { spoken ->
            interpretVoice(spoken)
        }
    }

    Surface(color = Bg, modifier = Modifier.fillMaxSize()) {
        Box(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(scroll)
                    .padding(start = 12.dp, end = 12.dp, top = 10.dp, bottom = 92.dp)
            ) {
                CompactHeader(
                    status = when {
                        connected -> "ONLINE"
                        connecting -> "CONNECTING"
                        else -> "OFFLINE"
                    },
                    selectedName = selectedDevice?.safeName() ?: "Nije izabran"
                )

                Spacer(Modifier.height(10.dp))

                MetricsGrid(
                    connected = connected,
                    lastCommand = lastCommand,
                    lastAck = lastAck,
                    lastRx = lastRx,
                    servo1 = servo1,
                    servo2 = servo2,
                    grip = grip
                )

                Spacer(Modifier.height(10.dp))

                BluetoothCard(
                    devices = devices,
                    selectedDevice = selectedDevice,
                    connected = connected,
                    connecting = connecting,
                    onRefresh = {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        devices = getDevices()
                        log("INFO", "Lista uparenih uređaja osvježena")
                    },
                    onSelect = {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        selectedDevice = it
                    },
                    onConnect = {
                        val dev = selectedDevice
                        if (dev == null) {
                            log("WARN", "Nije izabran Bluetooth uređaj")
                        } else {
                            scope.launch {
                                connecting = true
                                log("INFO", "Povezivanje na ${dev.safeName()}...")
                                val ok = connectDevice(dev)
                                connected = ok
                                connecting = false

                                if (ok) {
                                    log("OK", "Povezano na ${dev.safeName()}")
                                    delay(250)
                                    send("?", "PING / STATE")
                                } else {
                                    log("ERROR", "Povezivanje nije uspjelo")
                                }
                            }
                        }
                    },
                    onDisconnect = {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        disconnect()
                        connected = false
                        connecting = false
                        log("INFO", "Konekcija prekinuta")
                    }
                )

                Spacer(Modifier.height(10.dp))

                MainControls(
                    enabled = connected,
                    onGrab = { sendAndPreview("g", "UHVATI") },
                    onStop = { sendAndPreview("f", "E-STOP / PUSTI", urgent = true) },
                    onHome = { sendAndPreview("h", "HOME") },
                    onOpen = { sendAndPreview("o", "OTVORI") },
                    onClose = { sendAndPreview("c", "ZATEGNI") },
                    onTest1 = { send("1", "TEST S1") },
                    onTest2 = { send("2", "TEST S2") },
                    onPing = { send("?", "PING / STATE") }
                )

                Spacer(Modifier.height(10.dp))

                DigitalTwinCard(grip = grip)

                Spacer(Modifier.height(10.dp))

                CalibrationCard(
                    enabled = connected,
                    live = liveCalibration,
                    servo1 = servo1,
                    servo2 = servo2,
                    onLiveChange = {
                        liveCalibration = it
                        log("INFO", if (it) "LIVE kalibracija uključena" else "LIVE kalibracija isključena")
                    },
                    onServo1Change = { value ->
                        servo1 = value
                        updateGripFromServos()
                        if (liveCalibration) {
                            send("A${value.toInt().toString().padStart(3, '0')}", "S1 ${value.toInt()}°")
                        }
                    },
                    onServo2Change = { value ->
                        servo2 = value
                        updateGripFromServos()
                        if (liveCalibration) {
                            send("B${value.toInt().toString().padStart(3, '0')}", "S2 ${value.toInt()}°")
                        }
                    },
                    onApplyBoth = {
                        val a = servo1.toInt().toString().padStart(3, '0')
                        val b = servo2.toInt().toString().padStart(3, '0')
                        if (send("A$a", "Servo 1 ${servo1.toInt()}°")) {
                            scope.launch {
                                delay(180)
                                send("B$b", "Servo 2 ${servo2.toInt()}°")
                            }
                        }
                    },
                    onHomeSet = {
                        servo1 = SERVO1_HOME
                        servo2 = SERVO2_HOME
                        updateGripFromServos()
                    },
                    onGripSet = {
                        servo1 = SERVO1_GRIP
                        servo2 = SERVO2_GRIP
                        updateGripFromServos()
                    }
                )

                Spacer(Modifier.height(10.dp))

                VoiceAssistantCard(
                    enabled = connected,
                    lastVoice = lastVoice,
                    assistantText = assistantText,
                    hasPending = pendingVoiceCommand != null,
                    onListen = {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        startVoiceRecognition()
                    },
                    onConfirm = {
                        val cmd = pendingVoiceCommand
                        val label = pendingVoiceLabel
                        if (cmd != null && label != null) {
                            sendAndPreview(cmd, label, urgent = cmd == "f")
                            pendingVoiceCommand = null
                            pendingVoiceLabel = null
                            assistantText = "Komanda potvrđena: $label"
                        }
                    },
                    onCancel = {
                        pendingVoiceCommand = null
                        pendingVoiceLabel = null
                        assistantText = "Prijedlog poništen."
                        log("ASSIST", "Voice prijedlog poništen")
                    }
                )

                Spacer(Modifier.height(10.dp))

                HardwareCard()

                Spacer(Modifier.height(10.dp))

                LogCard(logs = logs)
            }

            EmergencyStopBar(
                enabled = connected,
                onStop = {
                    haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    sendAndPreview("f", "E-STOP / PUSTI", urgent = true)
                },
                modifier = Modifier.align(Alignment.BottomCenter)
            )
        }
    }
}

@Composable
fun CompactHeader(status: String, selectedName: String) {
    val color = when (status) {
        "ONLINE" -> Green
        "CONNECTING" -> Amber
        else -> Red
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Card, RoundedCornerShape(20.dp))
            .border(1.dp, Border.copy(alpha = 0.5f), RoundedCornerShape(20.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(34.dp)
                .clip(CircleShape)
                .background(color.copy(alpha = 0.16f))
                .border(1.dp, color.copy(alpha = 0.35f), CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Box(Modifier.size(11.dp).clip(CircleShape).background(color))
        }

        Spacer(Modifier.width(10.dp))

        Column(Modifier.weight(1f)) {
            Text("SPIROB GRAPPLER", color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.Black)
            Text(
                "STM32F103C8T6 • HC-06 • $selectedName",
                color = TextMuted,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }

        StatusBadge(status, color)
    }
}

@Composable
fun StatusBadge(text: String, color: Color) {
    Box(
        modifier = Modifier
            .background(color.copy(alpha = 0.16f), RoundedCornerShape(999.dp))
            .border(1.dp, color.copy(alpha = 0.35f), RoundedCornerShape(999.dp))
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) {
        Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun MetricsGrid(
    connected: Boolean,
    lastCommand: String,
    lastAck: String,
    lastRx: String,
    servo1: Float,
    servo2: Float,
    grip: Int
) {
    Column {
        Row {
            MetricBox("LINK", if (connected) "Online" else "Offline", if (connected) Green else Red, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            MetricBox("GRIP", "$grip%", Green, Modifier.weight(1f))
        }

        Spacer(Modifier.height(8.dp))

        Row {
            MetricBox("S1", "${servo1.toInt()}°", Amber, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            MetricBox("S2", "${servo2.toInt()}°", Amber, Modifier.weight(1f))
        }

        Spacer(Modifier.height(8.dp))

        Row {
            MetricBox("TX", lastCommand, Blue, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            MetricBox("ACK", lastAck, Green, Modifier.weight(1f))
        }

        Spacer(Modifier.height(8.dp))

        MetricBox("RX", lastRx, Color(0xFF60A5FA), Modifier.fillMaxWidth())
    }
}

@Composable
fun MetricBox(label: String, value: String, color: Color, modifier: Modifier) {
    Column(
        modifier = modifier
            .background(Card, RoundedCornerShape(18.dp))
            .border(1.dp, Border.copy(alpha = 0.42f), RoundedCornerShape(18.dp))
            .padding(13.dp)
    ) {
        Text(label, color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(3.dp))
        Text(
            value,
            color = color,
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
fun BluetoothCard(
    devices: List<BluetoothDevice>,
    selectedDevice: BluetoothDevice?,
    connected: Boolean,
    connecting: Boolean,
    onRefresh: () -> Unit,
    onSelect: (BluetoothDevice) -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit
) {
    CardSurface {
        SectionTitle("Bluetooth veza")
        Spacer(Modifier.height(10.dp))

        Row {
            ActionButton("OSVJEŽI", true, Blue, onRefresh, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            ActionButton(if (connecting) "ČEKAJ" else "POVEŽI", !connected && !connecting, Blue, onConnect, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            ActionButton("PREKINI", connected, Slate, onDisconnect, Modifier.weight(1f))
        }

        Spacer(Modifier.height(12.dp))

        if (devices.isEmpty()) {
            Text(
                "Nema uparenih uređaja. Prvo upari HC-06 u Bluetooth postavkama telefona, pa klikni OSVJEŽI.",
                color = TextMuted,
                fontSize = 12.sp
            )
        } else {
            LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 180.dp)) {
                items(devices) { device ->
                    DeviceItem(device, selectedDevice?.address == device.address) { onSelect(device) }
                    Spacer(Modifier.height(7.dp))
                }
            }
        }
    }
}

@Composable
fun MainControls(
    enabled: Boolean,
    onGrab: () -> Unit,
    onStop: () -> Unit,
    onHome: () -> Unit,
    onOpen: () -> Unit,
    onClose: () -> Unit,
    onTest1: () -> Unit,
    onTest2: () -> Unit,
    onPing: () -> Unit
) {
    CardSurface {
        SectionTitle("Upravljanje")
        Spacer(Modifier.height(10.dp))

        Button(
            onClick = onGrab,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Blue, disabledContainerColor = Disabled)
        ) {
            Text("UHVATI", color = Color.White, fontWeight = FontWeight.Black, fontSize = 16.sp)
        }

        Spacer(Modifier.height(10.dp))

        Row {
            SmallCommand("HOME", Slate, enabled, onHome, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("OTVORI", Slate, enabled, onOpen, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("ZATEGNI", Slate, enabled, onClose, Modifier.weight(1f))
        }

        Spacer(Modifier.height(8.dp))

        Row {
            SmallCommand("TEST S1", Amber, enabled, onTest1, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("TEST S2", Amber, enabled, onTest2, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("PING", Amber, enabled, onPing, Modifier.weight(1f))
        }

        Spacer(Modifier.height(8.dp))

        Button(
            onClick = onStop,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Red, disabledContainerColor = Disabled)
        ) {
            Text("E-STOP / PUSTI", color = Color.White, fontWeight = FontWeight.Black, fontSize = 14.sp)
        }
    }
}

@Composable
fun DigitalTwinCard(grip: Int) {
    val animatedGrip by animateFloatAsState(grip.toFloat(), animationSpec = tween(350), label = "grip")

    CardSurface {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("Digital Twin")
            Spacer(Modifier.weight(1f))
            Text(
                "Grip ${animatedGrip.toInt()}%",
                color = Green,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
                fontSize = 13.sp
            )
        }

        Spacer(Modifier.height(10.dp))

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(CardDark, RoundedCornerShape(22.dp))
                .border(1.dp, Border.copy(alpha = 0.45f), RoundedCornerShape(22.dp))
                .padding(12.dp)
        ) {
            Canvas(modifier = Modifier.fillMaxWidth().height(230.dp)) {
                val cx = size.width / 2f
                val cy = size.height / 2f + 6f
                val ratio = (animatedGrip / 100f).coerceIn(0f, 1f)

                val core = 50f
                val joint = 62f
                val seg1 = 58f
                val seg2 = 35f

                val limbColor = when {
                    ratio < 0.45f -> Color(0xFF60A5FA)
                    ratio < 0.80f -> Color(0xFFFACC15)
                    else -> Green
                }

                drawCircle(Color(0xFF1E293B), radius = core, center = Offset(cx, cy), style = Stroke(width = 2.5f))
                drawCircle(Color(0xFF0F172A), radius = core - 12f, center = Offset(cx, cy))

                for (i in 0 until 6) {
                    val a = Math.toRadians((i * 60 - 90).toDouble())
                    val curl = Math.toRadians((16 + 50 * ratio).toDouble())

                    val x0 = cx + cos(a).toFloat() * joint
                    val y0 = cy + sin(a).toFloat() * joint
                    val x1 = x0 + cos(a + curl).toFloat() * seg1
                    val y1 = y0 + sin(a + curl).toFloat() * seg1
                    val x2 = x1 + cos(a + curl * 1.35).toFloat() * seg2
                    val y2 = y1 + sin(a + curl * 1.35).toFloat() * seg2

                    drawLine(limbColor, Offset(x0, y0), Offset(x1, y1), strokeWidth = 6f, cap = StrokeCap.Round)
                    drawLine(limbColor, Offset(x1, y1), Offset(x2, y2), strokeWidth = 4f, cap = StrokeCap.Round)
                    drawCircle(Color(0xFFCBD5E1), radius = 4.5f, center = Offset(x0, y0))
                    drawCircle(limbColor, radius = 3.5f, center = Offset(x2, y2))
                }
            }
        }
    }
}

@Composable
fun CalibrationCard(
    enabled: Boolean,
    live: Boolean,
    servo1: Float,
    servo2: Float,
    onLiveChange: (Boolean) -> Unit,
    onServo1Change: (Float) -> Unit,
    onServo2Change: (Float) -> Unit,
    onApplyBoth: () -> Unit,
    onHomeSet: () -> Unit,
    onGripSet: () -> Unit
) {
    CardSurface {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("Kalibracija pokreta")
            Spacer(Modifier.weight(1f))
            Text("LIVE", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(6.dp))
            Switch(checked = live, onCheckedChange = onLiveChange, enabled = enabled)
        }

        Text(
            if (live)
                "LIVE uključen: servo se pomjera dok pomjeraš slider."
            else
                "Sigurno: slider mijenja preview, komanda ide tek na PRIMIJENI OBA.",
            color = if (live) Amber else TextMuted,
            fontSize = 11.sp
        )

        Spacer(Modifier.height(12.dp))

        ServoSlider("Servo 1", "PA0", servo1, enabled, onServo1Change)
        Spacer(Modifier.height(12.dp))
        ServoSlider("Servo 2", "PA1", servo2, enabled, onServo2Change)

        Spacer(Modifier.height(10.dp))

        Row {
            SmallCommand("PRIMIJENI", Blue, enabled, onApplyBoth, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("HOME SET", Slate, enabled, onHomeSet, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("GRIP SET", Slate, enabled, onGripSet, Modifier.weight(1f))
        }
    }
}

@Composable
fun ServoSlider(
    label: String,
    pin: String,
    value: Float,
    enabled: Boolean,
    onChange: (Float) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(CardDark, RoundedCornerShape(18.dp))
            .border(1.dp, Border.copy(alpha = 0.35f), RoundedCornerShape(18.dp))
            .padding(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, color = TextMain, fontWeight = FontWeight.Bold, fontSize = 13.sp)
            Spacer(Modifier.width(8.dp))
            Text(pin, color = TextMuted, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
            Spacer(Modifier.weight(1f))
            Box(
                modifier = Modifier
                    .background(Color(0xFF1F2937), RoundedCornerShape(999.dp))
                    .padding(horizontal = 10.dp, vertical = 5.dp)
            ) {
                Text("${value.toInt()}°", color = Color(0xFFFACC15), fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
            }
        }

        Slider(value = value, onValueChange = onChange, valueRange = 0f..180f, enabled = enabled)

        Row {
            Text("0°", color = TextMuted, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
            Spacer(Modifier.weight(1f))
            Text("90°", color = TextMuted, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
            Spacer(Modifier.weight(1f))
            Text("180°", color = TextMuted, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun VoiceAssistantCard(
    enabled: Boolean,
    lastVoice: String,
    assistantText: String,
    hasPending: Boolean,
    onListen: () -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit
) {
    CardSurface {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                SectionTitle("Voice Safety Assistant")
                Text("Lokalno prepoznavanje: uhvati, pusti, home, otvori, zategni, ping.", color = TextMuted, fontSize = 11.sp)
            }

            Spacer(Modifier.width(8.dp))

            Button(
                onClick = onListen,
                enabled = enabled,
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Blue, disabledContainerColor = Disabled),
                contentPadding = PaddingValues(horizontal = 14.dp),
                modifier = Modifier.height(46.dp)
            ) {
                Text("SLUŠAJ", color = Color.White, fontWeight = FontWeight.Black, fontSize = 12.sp)
            }
        }

        Spacer(Modifier.height(10.dp))

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(CardDark, RoundedCornerShape(16.dp))
                .border(1.dp, Border.copy(alpha = 0.35f), RoundedCornerShape(16.dp))
                .padding(10.dp)
        ) {
            Text("Govor: $lastVoice", color = TextMain, fontFamily = FontFamily.Monospace, fontSize = 10.sp, maxLines = 2)
            Spacer(Modifier.height(4.dp))
            Text(
                assistantText,
                color = if (hasPending) Amber else TextMuted,
                fontFamily = FontFamily.Monospace,
                fontSize = 10.sp,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis
            )
        }

        Spacer(Modifier.height(10.dp))

        Row {
            SmallCommand("POTVRDI", Green, enabled && hasPending, onConfirm, Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            SmallCommand("PONIŠTI", Slate, hasPending, onCancel, Modifier.weight(1f))
        }
    }
}

@Composable
fun HardwareCard() {
    CardSurface {
        SectionTitle("Hardver mapa")
        Spacer(Modifier.height(8.dp))

        HardwareRow("MCU", "STM32F103C8T6")
        HardwareRow("Bluetooth", "HC-06")
        HardwareRow("Baud", "9600")
        HardwareRow("BT TX/RX", "PA9 / PA10")
        HardwareRow("Servo 1", "PA0")
        HardwareRow("Servo 2", "PA1")
        HardwareRow("Napajanje", "serva vanjski 5V/6V")
        HardwareRow("GND", "zajednička masa")
    }
}

@Composable
fun HardwareRow(name: String, value: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text("$name:", color = TextMuted, fontFamily = FontFamily.Monospace, fontSize = 11.sp, modifier = Modifier.width(96.dp))
        Text(value, color = TextMain, fontFamily = FontFamily.Monospace, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun LogCard(logs: List<String>) {
    CardSurface {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("Log")
            Spacer(Modifier.weight(1f))
            Text("${logs.size}", color = TextMuted, fontFamily = FontFamily.Monospace, fontSize = 11.sp)
        }

        Spacer(Modifier.height(8.dp))

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(160.dp)
                .background(Color(0xFF020617), RoundedCornerShape(18.dp))
                .border(1.dp, Border.copy(alpha = 0.35f), RoundedCornerShape(18.dp))
                .padding(10.dp)
        ) {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(logs) { line ->
                    Text(
                        line,
                        color = Color(0xFFE5E7EB),
                        fontFamily = FontFamily.Monospace,
                        fontSize = 9.sp,
                        lineHeight = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

@Composable
fun EmergencyStopBar(enabled: Boolean, onStop: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .background(Bg.copy(alpha = 0.98f))
            .padding(horizontal = 12.dp, vertical = 9.dp)
    ) {
        Button(
            onClick = onStop,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().height(58.dp),
            shape = RoundedCornerShape(20.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Red, disabledContainerColor = Disabled)
        ) {
            Text("EMERGENCY STOP", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
fun SmallCommand(
    text: String,
    color: Color,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(46.dp),
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color, disabledContainerColor = Disabled),
        contentPadding = PaddingValues(horizontal = 4.dp)
    ) {
        Text(text, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 11.sp, maxLines = 1, textAlign = TextAlign.Center)
    }
}

@Composable
fun ActionButton(
    text: String,
    enabled: Boolean,
    color: Color,
    onClick: () -> Unit,
    modifier: Modifier
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(44.dp),
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color, disabledContainerColor = Disabled),
        contentPadding = PaddingValues(horizontal = 4.dp)
    ) {
        Text(text, color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}

@Composable
fun DeviceItem(device: BluetoothDevice, selected: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(if (selected) Blue.copy(alpha = 0.22f) else CardDark)
            .border(1.dp, if (selected) Blue else Border.copy(alpha = 0.45f), RoundedCornerShape(16.dp))
            .clickable { onClick() }
            .padding(13.dp)
    ) {
        Column {
            Text(device.safeName(), color = TextMain, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(device.address, color = TextMuted, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
        }
    }
}

@Composable
fun SectionTitle(text: String) {
    Text(text, color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.Bold)
}

@Composable
fun CardSurface(content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Card, RoundedCornerShape(22.dp))
            .border(1.dp, Border.copy(alpha = 0.42f), RoundedCornerShape(22.dp))
            .padding(14.dp),
        content = content
    )
}

fun gripIntensity(s1: Float, s2: Float): Int {
    val p1 = ((SERVO1_HOME - s1) / (SERVO1_HOME - SERVO1_GRIP)).coerceIn(0f, 1f)
    val p2 = ((s2 - SERVO2_HOME) / (SERVO2_GRIP - SERVO2_HOME)).coerceIn(0f, 1f)
    return (((p1 + p2) / 2f) * 100f).toInt()
}

fun BluetoothDevice.safeName(): String {
    return try {
        name ?: "Nepoznat uređaj"
    } catch (_: SecurityException) {
        "Bluetooth uređaj"
    }
}

@Composable
fun GrapplerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Blue,
            background = Bg,
            surface = Card,
            onPrimary = Color.White,
            onBackground = Color.White,
            onSurface = Color.White
        ),
        content = content
    )
}
