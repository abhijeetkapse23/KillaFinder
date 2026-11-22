# Killa Finder – setup

Offline app: shows all 260 Maharashtra forts sorted by distance from your live location. Tap a fort to open Google Maps directions. No server needed.

## 1. Install (one time)
- Install **Flutter**: https://docs.flutter.dev/get-started/install (choose Android)
- Install **Android Studio** (comes with the Android SDK). Run `flutter doctor` until it shows no errors.

## 2. Create the project
```
flutter create --org com.yourname fort_finder
```
Then copy these files from the zip into that new folder, replacing what's there:
- `pubspec.yaml`
- `lib/main.dart`
- `assets/forts.json` (create the `assets` folder)

Run:
```
cd fort_finder
flutter pub get
```

## 3. Add location permission
Open `android/app/src/main/AndroidManifest.xml` and add these two lines **just above** `<application`:
```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
```
Inside the existing `<queries>` block (near the bottom), add:
```xml
<intent>
    <action android:name="android.intent.action.VIEW"/>
    <data android:scheme="https"/>
</intent>
```
Change the app name: in the same file, set `android:label="Killa Finder"`.

## 4. Run on your phone
Turn on USB debugging on your phone, connect it, then:
```
flutter run
```

## 5. Build for Play Store
1. Create an upload key and set up signing: https://docs.flutter.dev/deployment/android#sign-the-app
2. `flutter build appbundle` → upload `build/app/outputs/bundle/release/app-release.aab`
3. Play Console needs: a privacy policy URL (say location is used only on the phone and never sent anywhere), screenshots, app icon, and the location-permission declaration.

## Editing fort data
`assets/forts.json` – one entry per fort:
```json
{"name":"Sinhagad","district":"Pune","lat":18.36639,"lon":73.75583,"trek":"~300 steps (Top) / Trail · Easy-Moderate","approx":false,"type":"fort"}
```
`approx: true` shows "Approx. location" in the app. 11 forts are marked like this: Gondhanapur, Jamner, Mailagad, Mankigad, Nandoshi, Narsimhagad, Palashi, Pimpalgaon Raja, Pimpaldoh, Sakharkherda and Virathan. Fix their coordinates when you can.

## Data sources
Fort coordinates are checked against OpenStreetMap (© OpenStreetMap contributors, ODbL) and Wikidata (CC0) by the "Fix coordinates" GitHub workflow. Results are in `COORDINATE_REPORT.md`.
