// Die Hülle: zeigt die Web-App in einer WebView und verbindet sie mit dem nativen Teil.
//
// Warum eine WebView statt die Oberfläche in Flutter neu zu bauen? Die Web-App kann schon alles
// anzeigen (Liste, Details, Suche, Einstellungen) und lernt in den nächsten Phasen noch viel
// dazu. Jede neue Funktion wird so nur EINMAL gebaut und steht auf Handy, Laptop-Browser und
// hier gleichzeitig zur Verfügung. Nativ bleibt nur, was ein Browser nicht kann.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:record/record.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'app_services.dart';
import 'bridge/native_bridge.dart';
import 'config.dart' as config;
import 'services/recording_controller.dart';

/// Zum Entwickeln lässt sich die Adresse überschreiben, z. B. für den Entwicklungsserver am PC:
///   flutter run --dart-define=WEB_URL=http://localhost:5180/Dictum/
/// (zusammen mit `adb reverse tcp:5180 tcp:5180`, damit "localhost" am Handy den PC meint)
const _webUrl = String.fromEnvironment('WEB_URL', defaultValue: config.webUrl);

class Shell extends StatefulWidget {
  const Shell({super.key, required this.services});

  final AppServices services;

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> with WidgetsBindingObserver {
  late final WebViewController _web;
  late final BridgeHandler _bridge;
  StreamSubscription<Map<String, Object?>>? _events;
  bool _pageLoaded = false;

  AppServices get _services => widget.services;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final host = Uri.parse(_webUrl).host;
    final dark = WidgetsBinding.instance.platformDispatcher.platformBrightness == Brightness.dark;

    _bridge = _services.bridge(_push);
    _web = WebViewController(onPermissionRequest: _onPermissionRequest)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      // Hintergrundfarbe passend zum System, damit beim Laden kein weißer Blitz erscheint
      ..setBackgroundColor(dark ? const Color(0xFF111114) : const Color(0xFFF6F6F8))
      ..addJavaScriptChannel('DictumNative', onMessageReceived: (m) => _bridge.handle(m.message))
      ..setNavigationDelegate(NavigationDelegate(
        // Nur die eigene Web-App darf geladen werden: Die Brücke (Aufnahme, Anmeldedaten) soll
        // keiner fremden Seite zur Verfügung stehen
        onNavigationRequest: (request) {
          final uri = Uri.tryParse(request.url);
          return uri != null && uri.host == host ? NavigationDecision.navigate : NavigationDecision.prevent;
        },
        onPageFinished: (_) {
          _pageLoaded = true;
          _push(_services.controller.status()); // die Seite weiß sonst nichts vom aktuellen Zustand
        },
      ))
      ..loadRequest(Uri.parse(_webUrl));

    _events = _services.controller.events.listen(_push);
    _services.listenToNotification();
  }

  /// Die Web-App darf das Mikrofon nutzen (fürs Diktat in der Seite), sonst nichts.
  ///
  /// Zwei Schlüssel müssen passen: Die WebView fragt die App ("darf die Seite das Mikrofon?"),
  /// und Android fragt den Nutzer ("darf die App das Mikrofon?"). Würde man der Seite nur
  /// zusagen, ohne die Android-Erlaubnis zu haben, scheitert die Aufnahme in der Seite lautlos.
  /// `hasPermission()` zeigt beim ersten Mal den Android-Dialog.
  Future<void> _onPermissionRequest(WebViewPermissionRequest request) async {
    final onlyMic = request.types.every((t) => t == WebViewPermissionResourceType.microphone);
    if (!onlyMic) {
      await request.deny();
      return;
    }
    final recorder = AudioRecorder();
    final granted = await recorder.hasPermission();
    await recorder.dispose();
    granted ? await request.grant() : await request.deny();
  }

  /// Schickt ein Ereignis an die Web-App (sobald die Seite geladen ist).
  void _push(Map<String, Object?> event) {
    if (!_pageLoaded) return;
    _web.runJavaScript(eventScript(event));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_services.uploader.kick()); // zurück in der App: liegengebliebenes hochladen
      _push(_services.controller.status());
    }
  }

  /// Zurück-Taste: erst in der Web-App zurück. Am Anfang der App: Läuft eine Aufnahme, wird die
  /// App nur in den Hintergrund geschoben. Würde man sie beenden, endete auch die Aufnahme.
  Future<void> _onBack() async {
    if (await _web.canGoBack()) {
      await _web.goBack();
    } else if (_services.controller.state != RecState.idle) {
      FlutterForegroundTask.minimizeApp();
    } else {
      await SystemNavigator.pop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _events?.cancel();
    _services.stopListeningToNotification();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _onBack();
      },
      child: Scaffold(
        body: SafeArea(child: WebViewWidget(controller: _web)),
      ),
    );
  }
}
