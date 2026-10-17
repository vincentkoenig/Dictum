// Das "Zusammenstecken" aller Bausteine an EINER Stelle. Kein anderer Teil der App baut sich
// seine Abhängigkeiten selbst: Die Bausteine bekommen sie übergeben. Das macht sie in Tests
// austauschbar (siehe test/) und lässt auf einen Blick erkennen, was womit zusammenhängt.

import 'dart:async';
import 'dart:io';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:path_provider/path_provider.dart';

import 'bridge/native_bridge.dart';
import 'config.dart' as config;
import 'services/background_service.dart';
import 'services/chunked_recorder.dart';
import 'services/cloud_client.dart';
import 'services/recording_controller.dart';
import 'services/secure_session_store.dart';
import 'services/upload_queue.dart';
import 'services/uploader.dart';

class AppServices {
  AppServices._({
    required this.cloud,
    required this.queue,
    required this.uploader,
    required this.controller,
  });

  final DictumCloud cloud;
  final UploadQueue queue;
  final Uploader uploader;
  final RecordingController controller;

  /// Baut alles zusammen und stellt den Zustand vom letzten Mal wieder her.
  static Future<AppServices> create() async {
    // Persistenter App-Ordner: Aufnahmen und Warteschlange müssen Neustarts überleben. Der
    // temporäre Ordner (getTemporaryDirectory) darf vom Betriebssystem jederzeit geleert werden.
    final docs = await getApplicationDocumentsDirectory();

    final cloud = DictumCloud(url: config.supabaseUrl, key: config.supabaseKey, store: SecureSessionStore());
    final queue = UploadQueue(Directory('${docs.path}/queue'));
    final uploader = Uploader(queue: queue, backend: cloud);
    final controller = RecordingController(
      queue: queue,
      uploader: uploader,
      service: ForegroundService(),
      sourceFactory: RecordPackageSource.new,
      workDir: Directory('${docs.path}/recording'),
      hasSession: () => cloud.hasSession,
    );
    final services = AppServices._(cloud: cloud, queue: queue, uploader: uploader, controller: controller);
    unawaited(services._restore());
    return services;
  }

  Future<void> _restore() async {
    try {
      await cloud.restore(); // mit dem gespeicherten Token wieder anmelden
    } catch (_) {
      // kein Netz: das Token bleibt gespeichert, der Uploader versucht es später nochmal
    }
    await controller.recoverInterrupted();
    unawaited(uploader.kick());
  }

  /// Der "Stopp"-Knopf in der Benachrichtigung des Mikrofon-Dienstes.
  void _onServiceMessage(Object data) {
    if (data == ForegroundService.stopMessage) unawaited(controller.stop());
  }

  void listenToNotification() => FlutterForegroundTask.addTaskDataCallback(_onServiceMessage);

  void stopListeningToNotification() => FlutterForegroundTask.removeTaskDataCallback(_onServiceMessage);

  BridgeHandler bridge(void Function(Map<String, Object?>) emit) =>
      BridgeHandler(auth: cloud, controller: controller, uploader: uploader, emit: emit);
}
