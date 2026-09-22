# MedList Native for Android

An installable Android WebView wrapper for https://medlist-new.vercel.app.
**WhatsApp / Files → Share → MedList Native** uses Android's content URI grant and
a native HTTPS multipart upload. It does not use Chrome's PWA share target or
service worker. The existing server validates the file and returns the existing
destination chooser (Make HTML, Search, etc.). Website changes appear without
rebuilding the APK; native changes require an APK update.

## Install the test APK

1. On GitHub, open **Actions → Android APK → latest successful run**.
2. Download the **MedList-Native-APK** artifact, unzip it, and copy `app-debug.apk`
   to your Android phone.
3. Open the APK and allow installation from that source if Android asks.
4. Open **MedList Native** once. Share one HTM document from WhatsApp or Files and
   select **MedList Native** (not the existing MedList PWA).
5. The file-received page should show its filename and size. Choose Make HTML.

The test APK is debug-signed. This is not a Play Store release. Separate CI runs
may use different debug keys; uninstall an older test APK if Android reports a
signature conflict (this clears the native app's local data). For permanent
distribution, generate and securely retain a release signing key in Android
Studio. Never commit a signing key or password. The PWA can remain installed.

## Build locally

Requirements: JDK 17, Gradle **8.9**, Android SDK platform **35**, build tools
**34.0.0**. Open this `android` folder in Android Studio and use a local Gradle
8.9 installation, or run from this folder:

```powershell
gradle testDebugUnitTest lintDebug assembleDebug
```

Set the SDK location using Android Studio or an untracked `local.properties`
containing `sdk.dir=...`. Output: `app/build/outputs/apk/debug/app-debug.apk`.
The GitHub workflow installs the toolchain, runs tests and lint, then builds the APK.

## Behavior and limits

- Android 8.0 or later; an up-to-date Android System WebView is required.
- Internet access is required. This bypasses the PWA receiving path, not hosting
  limits or outages. Native upload uses the existing `/share-target` endpoint.
- One document per share. Multiple-file shares are explicitly rejected so files
  cannot be silently discarded. The MIME filter is broad because Android file
  providers sometimes mislabel HTM files. The server accepts HTML/HTM, PDF or TXT.
- Extensionless names are passed to the server for its existing content detection.
- Files are staged in private cache while the Android permission is valid. A
  failed network upload offers Retry without asking the sender for the file again.
  A successful upload deletes its cached attachment. Abandoned files expire after
  24 hours on the next app launch. Cached data is excluded from Android backup.
- The native file ceiling is 15 MiB to leave multipart overhead below the server's
  16 MiB limit. The hosting platform may impose a lower limit; HTTP 413 is shown.
- Existing web file pickers work through Android's document picker. Server
  downloads and same-origin blob downloads use Android's Save As picker.
- Only the configured HTTPS site opens inside the WebView. External web links
  open in the browser. Local file navigation, mixed content, and third-party
  cookies are disabled. No JavaScript interface is exposed to website frames.
- Process termination during an active transfer may require sharing again; this
  is an activity-based uploader, not a persistent background upload service.

## Device acceptance checks (required before calling sharing fixed)

1. Cold start: share the previously failing approximately 2.9 MB HTM from WhatsApp.
   Verify filename, size and parsed medicine list in Make HTML.
2. Warm start: repeat from Files while the native app is already open.
3. Share an extensionless HTML file. Verify the server recovers `.htm`.
4. Test PDF and TXT, plus an empty or unsupported binary document.
5. Disable connectivity, share, restore connectivity, then tap Retry.
6. Share two files together: verify a clear message and no partial upload.
7. Rotate, use Back/Home, and share a second file after the first finishes.
8. Use Upload New File and save a generated HTML plus a client-generated TXT.
9. Repeat on the second phone. Keep the PWA result separate from native results.

Automated unit tests cover exact origin restrictions, multipart header injection,
binary byte preservation, extensionless names, and size limits. These checks do
not replace testing actual Android content grants from WhatsApp on your phone.

### Local share receipt (v1.3)
The native receiver stages the granted URI in private cache, builds a bundled
chooser locally, and uses the website origin for IndexedDB. No attachment POST
or chooser download is needed. Selecting a destination stores the file locally
and opens the existing tool; that tool may upload when processing is requested.
The chooser works offline; online tools still need connectivity.

Run `python android/tools/bundle_share.py` from the repository root after changing
`templates/shared_file.html` or `static/shared-store.js`, then commit the generated
`android/app/src/main/assets/share.html`. Raw document HTML is never executed.
