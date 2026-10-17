// Einstiegspunkt der Android-App.
//
// Aufbau in einem Satz: Eine WebView zeigt die Web-App (shell.dart), und der native Teil
// (services/) nimmt im Hintergrund auf und lädt hoch. Beide sprechen über die Brücke
// (bridge/native_bridge.dart). Erklärung im Überblick: docs/mobile.md.

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'app_services.dart';
import 'services/background_service.dart';
import 'shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Kommunikationsweg zwischen Dienst (Benachrichtigungs-Knopf) und App
  FlutterForegroundTask.initCommunicationPort();
  ForegroundService.init();
  final services = await AppServices.create();
  runApp(DictumApp(services: services));
}

class DictumApp extends StatelessWidget {
  const DictumApp({super.key, required this.services});

  final AppServices services;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Dictum',
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.system,
      theme: ThemeData(colorSchemeSeed: const Color(0xFF4F46E5), useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: const Color(0xFF7C74FF), brightness: Brightness.dark, useMaterial3: true),
      home: Shell(services: services),
    );
  }
}
