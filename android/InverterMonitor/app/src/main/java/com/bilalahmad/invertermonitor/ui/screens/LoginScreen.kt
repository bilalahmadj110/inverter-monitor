package com.bilalahmad.invertermonitor.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bilalahmad.invertermonitor.data.viewmodels.AuthState
import com.bilalahmad.invertermonitor.data.viewmodels.AuthViewModel
import com.bilalahmad.invertermonitor.ui.components.SheetScaffold
import com.bilalahmad.invertermonitor.ui.components.SheetSectionHeader
import com.bilalahmad.invertermonitor.ui.components.card
import com.bilalahmad.invertermonitor.ui.theme.Palette

@Composable
fun LoginScreen(auth: AuthViewModel) {
    // Credentials held locally — TextField value/onValueChange is the standard
    // Compose pattern and avoids StateFlow latency / autofill timing glitches.
    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }

    val loginError by auth.loginError.collectAsStateWithLifecycle()
    val state by auth.state.collectAsStateWithLifecycle()
    val isBusy = state == AuthState.SigningIn

    val serverURL by auth.settings.serverURL.collectAsStateWithLifecycle()
    var showServerEditor by remember { mutableStateOf(false) }
    val keyboard = LocalSoftwareKeyboardController.current

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Palette.BackgroundGradient)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .widthIn(max = 420.dp)
                .align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(60.dp))

            // Brand mark
            Icon(
                imageVector = Icons.Filled.WbSunny,
                contentDescription = null,
                tint = Palette.Solar,
                modifier = Modifier.size(52.dp).shadow(18.dp, clip = false),
            )
            Spacer(Modifier.height(10.dp))
            Text("Inverter Monitor", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Color.White)
            Spacer(Modifier.height(4.dp))
            Text("Sign in to continue", fontSize = 12.sp, color = Palette.MutedText)

            Spacer(Modifier.height(20.dp))

            // Card
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .card(cornerRadius = 18)
                    .padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                if (loginError != null) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(Color(0x26FF4D4D))
                            .border(BorderStroke(1.dp, Color(0x66FF4D4D)), RoundedCornerShape(10.dp))
                            .padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(Icons.Filled.Warning, contentDescription = null,
                             tint = Color(0xFFFECACA), modifier = Modifier.size(16.dp))
                        Text(loginError!!, fontSize = 13.sp, color = Color(0xFFFECACA))
                    }
                }

                LabeledField(label = "Username") {
                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        placeholder = { Text("admin", color = Palette.SubtleText) },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Ascii,
                            imeAction = ImeAction.Next,
                            autoCorrectEnabled = false,
                        ),
                        colors = fieldColors(),
                    )
                }

                LabeledField(label = "Password") {
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        placeholder = { Text("••••••••", color = Palette.SubtleText) },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Go,
                        ),
                        keyboardActions = KeyboardActions(onGo = {
                            keyboard?.hide()
                            auth.signIn(username, password)
                        }),
                        colors = fieldColors(),
                    )
                }

                Button(
                    onClick = { keyboard?.hide(); auth.signIn(username, password) },
                    modifier = Modifier.fillMaxWidth().height(44.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF2563EB),
                        contentColor = Color.White,
                    ),
                    enabled = !isBusy,
                    shape = RoundedCornerShape(10.dp),
                ) {
                    if (isBusy) {
                        CircularProgressIndicator(
                            color = Color.White,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text("Sign in", fontWeight = FontWeight.SemiBold)
                }

                HorizontalDivider(color = Palette.Divider)

                Button(
                    onClick = { showServerEditor = true },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Palette.CardSurface,
                        contentColor = Palette.MutedText,
                    ),
                    shape = RoundedCornerShape(10.dp),
                ) {
                    Text(
                        serverURL,
                        fontSize = 12.sp,
                        maxLines = 1,
                        modifier = Modifier.weight(1f),
                        textAlign = TextAlign.Start,
                    )
                    Text("›", fontSize = 18.sp)
                }
            }

            Spacer(Modifier.height(40.dp))
        }
    }

    if (showServerEditor) {
        ServerURLEditorSheet(
            initial = serverURL,
            onSave = { auth.settings.setServerURL(it); showServerEditor = false },
            onDismiss = { showServerEditor = false },
        )
    }
}

@Composable
private fun LabeledField(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Palette.SubtleText)
        content()
    }
}

@Composable
private fun fieldColors() = TextFieldDefaults.colors(
    focusedTextColor = Color.White,
    unfocusedTextColor = Color.White,
    focusedContainerColor = Color(0x14FFFFFF),
    unfocusedContainerColor = Color(0x14FFFFFF),
    disabledContainerColor = Color(0x14FFFFFF),
    cursorColor = Palette.Solar,
    focusedIndicatorColor = Palette.Solar,
    unfocusedIndicatorColor = Palette.CardBorder,
)

@Composable
fun ServerURLEditorSheet(initial: String, onSave: (String) -> Unit, onDismiss: () -> Unit) {
    var url by remember { mutableStateOf(initial) }
    val trimmed = url.trim()

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = Palette.BackgroundTop,
    ) {
        SheetScaffold(
            icon = Icons.Filled.Dns,
            iconTint = Palette.Grid,
            title = "Server",
            subtitle = "Base URL of the Flask server",
            onDismiss = onDismiss,
        ) {
            SheetSectionHeader("URL", accent = Palette.Grid)
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = { Text("https://inverter.example.com") },
                colors = fieldColors(),
                shape = RoundedCornerShape(12.dp),
            )
            Text(
                "Scheme optional — HTTP is assumed when omitted. For LAN direct-IP access (http://…) the server needs BEHIND_PROXY=0 so session cookies aren't Secure-only.",
                fontSize = 11.sp,
                color = Palette.SubtleText,
                lineHeight = 16.sp,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onDismiss,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                ) { Text("Cancel") }
                Button(
                    onClick = { onSave(trimmed) },
                    modifier = Modifier.weight(1f).height(48.dp),
                    enabled = trimmed.isNotEmpty(),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Palette.Grid.copy(alpha = 0.24f),
                        contentColor = Palette.Grid,
                    ),
                ) { Text("Save", fontWeight = FontWeight.SemiBold) }
            }
        }
    }
}
