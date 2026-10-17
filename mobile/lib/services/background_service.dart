// Mikrofon-Dienst im Vordergrund: erlaubt die Aufnahme bei ausgeschaltetem Bildschirm.
// Dieselbe Technik wie in Khutba-Translation (mobile/lib/services/background_session_service.dart).
//
// Warum geht das nicht in einer PWA? Android erlaubt den Mikrofonzugriff im Hintergrund nur
// einem **Dienst im Vordergrund vom Typ "microphone"**, der gestartet wurde, während die App
// sichtbar war. Ein solcher Dienst zeigt eine dauerhafte Benachrichtigung (hier mit "Stopp"-Knopf)
// und gibt dem Prozess höhere Priorität sowie Wake- und WLAN-Sperren, damit weder die Aufnahme
// noch der Upload einschlafen.
//
// Der Dienst selbst arbeitet nicht: Die ganze Aufnahme läuft weiter im Hauptteil der App
// (RecordingController). Sein "Task" leitet nur den Druck auf den Benachrichtigungs-Knopf
// zurück an die App.

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

abstract interface class BackgroundService {
  Future<void> start({required String title, required String text, required String stopLabel});
  Future<void> stop();
}

class ForegroundService implements BackgroundService {
  static const stopButtonId = 'stop_recording';
  static const stopMessage = 'stop_recording';
  static const _serviceId = 4712;

  /// Einmal beim App-Start aufrufen.
  static void init() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'dictum_recording',
        channelName: 'Aufnahme',
        channelDescription: 'Wird angezeigt, solange Dictum aufnimmt.',
        // Niedrige Wichtigkeit: kein Ton, kein Aufpoppen – man sitzt womöglich im Meeting
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(showNotification: false, playSound: false),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        // Ein Mikrofon-Dienst darf ohnehin nicht aus dem Hintergrund gestartet werden, und ein
        // neu gestarteter Dienst ohne die Aufnahme der App wäre nutzlos
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  /// Muss aufgerufen werden, solange die App sichtbar ist. Wirft nie: Klappt der Dienst nicht,
  /// läuft die Aufnahme trotzdem, nur eben nicht im Hintergrund.
  @override
  Future<void> start({required String title, required String text, required String stopLabel}) async {
    try {
      // Android 13+: ohne diese Erlaubnis ist die Benachrichtigung (und ihr Stopp-Knopf)
      // unsichtbar, obwohl der Dienst läuft
      final permission = await FlutterForegroundTask.checkNotificationPermission();
      if (permission != NotificationPermission.granted) {
        await FlutterForegroundTask.requestNotificationPermission();
      }
      if (await FlutterForegroundTask.isRunningService) {
        await FlutterForegroundTask.stopService();
      }
      await FlutterForegroundTask.startService(
        serviceId: _serviceId,
        serviceTypes: [ForegroundServiceTypes.microphone],
        notificationTitle: title,
        notificationText: text,
        notificationButtons: [NotificationButton(id: stopButtonId, text: stopLabel)],
        callback: recordingServiceCallback,
      );
    } catch (_) {
      // Hintergrund-Betrieb ist ein Bonus, keine Voraussetzung
    }
  }

  @override
  Future<void> stop() async {
    try {
      if (await FlutterForegroundTask.isRunningService) {
        await FlutterForegroundTask.stopService();
      }
    } catch (_) {}
  }
}

@pragma('vm:entry-point')
void recordingServiceCallback() {
  FlutterForegroundTask.setTaskHandler(_RecordingTaskHandler());
}

class _RecordingTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}

  @override
  void onNotificationButtonPressed(String id) {
    if (id == ForegroundService.stopButtonId) {
      FlutterForegroundTask.sendDataToMain(ForegroundService.stopMessage);
    }
  }

  @override
  void onNotificationPressed() {
    FlutterForegroundTask.launchApp();
  }
}
