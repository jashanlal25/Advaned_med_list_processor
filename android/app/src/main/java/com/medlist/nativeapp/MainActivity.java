package com.medlist.nativeapp;

import android.annotation.SuppressLint;
import android.app.*;
import android.content.*;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.webkit.*;
import android.view.*;
import android.widget.*;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

public final class MainActivity extends Activity {
    private static final int PICK_FILE = 10, SAVE_FILE = 11;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private WebView web;
    private TextView status;
    private LinearLayout toolbar;
    private Button retry;
    private ValueCallback<Uri[]> fileCallback;
    private File pendingShare, pendingDownload;
    private String pendingName;
    private boolean busy;

    @SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(18, 34, 56));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setText("MedList Native");
        status.setPadding(8, 8, 8, 8);
        toolbar.addView(status, new LinearLayout.LayoutParams(0, -2, 1));
        retry = new Button(this);
        retry.setText("Retry");
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(view -> {
            if (pendingShare != null && pendingShare.exists()) openPending();
            else web.reload();
        });
        toolbar.addView(retry);
        toolbar.setVisibility(View.GONE);

        web = new WebView(this);
        FrameLayout content = new FrameLayout(this);
        content.addView(web, new FrameLayout.LayoutParams(-1, -1));
        int unit = Math.max(1, Math.round(getResources().getDisplayMetrics().density));
        ProgressBar spinner = new ProgressBar(this);
        toolbar.addView(spinner, 0, new LinearLayout.LayoutParams(24 * unit, 24 * unit));
        toolbar.setPadding(12 * unit, 4 * unit, 12 * unit, 4 * unit);
        toolbar.setBackgroundColor(Color.rgb(25, 43, 67));
        status.setTextSize(13);
        status.setMaxLines(2);
        FrameLayout.LayoutParams floating = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        floating.setMargins(16 * unit, 0, 16 * unit, 16 * unit);
        content.addView(toolbar, floating);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setUserAgentString(settings.getUserAgentString() + " MedListNative/1.3");
        // The existing website gates its persistent file batch on standalone mode.
        // Set this before page scripts run, only on the exact MedList origin.
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(web,
                "window.__MEDLIST_NATIVE__=true;Object.defineProperty(navigator,'standalone',{get:()=>true});",
                Collections.singleton(ShareUpload.ORIGIN));
        } else {
            new AlertDialog.Builder(this).setTitle("Update Android System WebView")
                .setMessage("Update Android System WebView in the Play Store to enable shared-file processing in this app.")
                .setPositiveButton("OK", null).show();
        }
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (ShareUpload.isTrusted(request.getUrl().toString())) return false;
                if (request.isForMainFrame()) openExternal(request.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                if (!busy) { toolbar.setVisibility(View.VISIBLE); status.setText("Opening…"); }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!busy && retry.getVisibility() != View.VISIBLE) toolbar.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && !busy) showError("Page could not load. Check your connection.");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!ShareUpload.isTrusted(view.getUrl())) return false;
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(pick, PICK_FILE); }
                catch (ActivityNotFoundException e) { fileCallback.onReceiveValue(null); fileCallback = null; }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, size) -> {
            if (busy || pendingDownload != null) { toast("Finish the current transfer first."); return; }
            if (!ShareUpload.isTrusted(web.getUrl())) return;
            String name = ShareUpload.safeName(URLUtil.guessFileName(url, disposition, mime));
            if (url.startsWith("blob:" + ShareUpload.ORIGIN + "/")) downloadBlob(url, name, mime);
            else if (ShareUpload.isTrusted(url)) downloadFile(url, name, mime);
        });
        // Saved WebView state avoids reposting a share when Android recreates this activity.
        if (state != null && web.restoreState(state) != null) {
            String cached = state.getString("pendingShare");
            if (cached != null) {
                File file = new File(getCacheDir(), cached);
                if (file.exists()) { pendingShare = file; pendingName = state.getString("pendingName", "shared_document");
                    showError("Tap Retry to reopen the saved attachment."); }
            }
        } else {
            if (IncomingShare.isShare(getIntent())) handleShare(getIntent());
            else web.loadUrl(ShareUpload.ORIGIN + "/");
        }
        // Cache is private and excluded from backups; expire abandoned transfer files.
        File[] old = getCacheDir().listFiles();
        if (old != null) for (File file : old)
            if (file.getName().startsWith("medlist-") && System.currentTimeMillis() - file.lastModified() > 86400000L) file.delete();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleShare(intent);
    }

    private void handleShare(Intent intent) {
        if (!IncomingShare.isShare(intent)) return;
        if (busy) { toast("A file is already transferring. Share the next file after it finishes."); return; }
        List<Uri> uris;
        try { uris = IncomingShare.files(intent); }
        catch (RuntimeException e) { showError("Android could not read this share. Send it again from Files."); return; }
        if (uris.isEmpty()) { showError("No attachment was supplied to the native app. Share the document itself."); return; }
        if (uris.size() != 1) { showError("Please share one document at a time; no files were uploaded."); return; }
        busy = true;
        retry.setVisibility(View.GONE);
        web.stopLoading();
        toolbar.setVisibility(View.VISIBLE);
        status.setText("Preparing file…");
        Uri uri = uris.get(0);
        worker.execute(() -> {
            File staged = null;
            try {
                String name = "shared_document";
                try (Cursor cursor = getContentResolver().query(uri,
                    new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                    if (cursor != null && cursor.moveToFirst()) name = cursor.getString(0);
                } catch (RuntimeException ignored) { /* Content can still be readable without metadata. */ }
                staged = File.createTempFile("medlist-share-", ".tmp", getCacheDir());
                try (InputStream input = getContentResolver().openInputStream(uri);
                     OutputStream output = new FileOutputStream(staged)) {
                    if (input == null) throw new IOException("The sending app did not grant access to this file.");
                    if (ShareUpload.copyLimited(input, output, ShareUpload.MAX_FILE_BYTES) == 0)
                        throw new IOException("The shared document is empty.");
                }
                File ready = staged;
                String filename = ShareUpload.safeName(name);
                runOnUiThread(() -> {
                    if (isDestroyed()) { ready.delete(); return; }
                    if (pendingShare != null) pendingShare.delete();
                    pendingShare = ready;
                    pendingName = filename;
                    busy = false;
                    openPending();
                });
            } catch (Exception e) {
                if (staged != null) staged.delete();
                fail(e instanceof SecurityException ? "Android denied access to the attachment. Share it again from Files."
                    : "Could not read attachment: " + safeMessage(e));
            }
        });
    }

    private void openPending() {
        if (busy || pendingShare == null) return;
        busy = true;
        retry.setVisibility(View.GONE);
        toolbar.setVisibility(View.VISIBLE);
        status.setText("Preparing file…");
        File file = pendingShare;
        String name = pendingName;
        worker.execute(() -> {
            try {
                byte[] bytes = LocalShare.readDocument(file);
                ByteArrayOutputStream template = new ByteArrayOutputStream();
                try (InputStream input = getAssets().open("share.html")) {
                    ShareUpload.copyLimited(input, template, 1024 * 1024);
                }
                String html = LocalShare.render(template.toString("UTF-8"), name, bytes);
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    busy = false;
                    toolbar.setVisibility(View.GONE);
                    // No network request: all chooser assets and document bytes are local.
                    // HTTPS base keeps the same IndexedDB as the online processing tools.
                    web.loadDataWithBaseURL(ShareUpload.ORIGIN + "/native-share", html,
                        "text/html", "UTF-8", ShareUpload.ORIGIN + "/native-share");
                    // Keep the private copy for retry/recreation; expire it after 24h.
                });
            } catch (Exception e) { fail("Could not prepare file: " + safeMessage(e) + " Tap Retry."); }
        });
    }

    private void downloadFile(String url, String name, String mime) {
        busy = true;
        toolbar.setVisibility(View.VISIBLE);
        status.setText("Preparing download…");
        String cookie = CookieManager.getInstance().getCookie(ShareUpload.ORIGIN);
        worker.execute(() -> {
            File staged = null;
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(url).openConnection();
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(20000);
                connection.setReadTimeout(90000);
                if (cookie != null) connection.setRequestProperty("Cookie", cookie);
                if (connection.getResponseCode() != 200) throw new IOException("Server returned HTTP " + connection.getResponseCode());
                staged = File.createTempFile("medlist-download-", ".tmp", getCacheDir());
                try (InputStream input = connection.getInputStream(); OutputStream output = new FileOutputStream(staged)) {
                    ShareUpload.copyLimited(input, output, ShareUpload.MAX_RESPONSE_BYTES);
                }
                File ready = staged;
                runOnUiThread(() -> offerSave(ready, name, mime));
            } catch (Exception e) {
                if (staged != null) staged.delete();
                fail("Download failed: " + safeMessage(e));
            } finally { if (connection != null) connection.disconnect(); }
        });
    }

    private void downloadBlob(String url, String name, String mime) {
        busy = true;
        toolbar.setVisibility(View.VISIBLE);
        status.setText("Preparing download…");
        // Read only the requested same-origin blob; no persistent JavaScript-to-native bridge.
        String token = "__medlistDownload" + UUID.randomUUID().toString().replace("-", "");
        String script = "(async()=>{try{const b=await(await fetch(" + JSONObject.quote(url)
            + ")).blob();if(b.size>15728640)throw Error('File too large');const r=new FileReader();"
            + "r.onload=()=>window['" + token + "']={data:r.result};r.onerror=()=>window['" + token
            + "']={error:true};r.readAsDataURL(b);}catch(e){window['" + token + "']={error:true};}})();";
        web.evaluateJavascript(script, ignored -> pollBlob(token, name, mime, 0));
    }

    private void pollBlob(String token, String name, String mime, int attempt) {
        if (isDestroyed()) return;
        if (!ShareUpload.isTrusted(web.getUrl()) || attempt > 60) { fail("Download interrupted. Please try again."); return; }
        web.evaluateJavascript("window['" + token + "']||null", result -> {
            if ("null".equals(result)) {
                web.postDelayed(() -> pollBlob(token, name, mime, attempt + 1), 250);
                return;
            }
            web.evaluateJavascript("delete window['" + token + "']", null);
            worker.execute(() -> {
                File staged = null;
                try {
                    JSONObject value = new JSONObject(result);
                    String data = value.getString("data");
                    int split = data.indexOf(',');
                    if (split < 0 || data.length() > 22 * 1024 * 1024) throw new IOException("Invalid download");
                    byte[] bytes = android.util.Base64.decode(data.substring(split + 1), android.util.Base64.DEFAULT);
                    staged = File.createTempFile("medlist-download-", ".tmp", getCacheDir());
                    try (OutputStream output = new FileOutputStream(staged)) { output.write(bytes); }
                    File ready = staged;
                    runOnUiThread(() -> offerSave(ready, name, mime));
                } catch (Exception e) { if (staged != null) staged.delete(); fail("Could not save the generated download. Try again."); }
            });
        });
    }

    private void offerSave(File file, String name, String mime) {
        if (isDestroyed()) { file.delete(); return; }
        busy = false;
        toolbar.setVisibility(View.GONE);
        pendingDownload = file;
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        save.addCategory(Intent.CATEGORY_OPENABLE);
        save.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
        save.putExtra(Intent.EXTRA_TITLE, name);
        try { startActivityForResult(save, SAVE_FILE); }
        catch (ActivityNotFoundException e) { file.delete(); pendingDownload = null; showError("No document saver is installed."); }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK_FILE && fileCallback != null) {
            List<Uri> uris = new ArrayList<>();
            if (result == RESULT_OK && data != null) {
                if (data.getClipData() != null) for (int i = 0; i < data.getClipData().getItemCount(); i++)
                    uris.add(data.getClipData().getItemAt(i).getUri());
                else if (data.getData() != null) uris.add(data.getData());
            }
            fileCallback.onReceiveValue(uris.isEmpty() ? null : uris.toArray(new Uri[0]));
            fileCallback = null;
        }
        if (request == SAVE_FILE && pendingDownload != null) {
            File file = pendingDownload;
            pendingDownload = null;
            if (result != RESULT_OK || data == null || data.getData() == null) { file.delete(); status.setText("Save cancelled"); return; }
            Uri uri = data.getData();
            busy = true;
            worker.execute(() -> {
                try (InputStream input = new FileInputStream(file); OutputStream output = getContentResolver().openOutputStream(uri)) {
                    if (output == null) throw new IOException("Cannot open save location");
                    ShareUpload.copyLimited(input, output, ShareUpload.MAX_RESPONSE_BYTES);
                    runOnUiThread(() -> { busy = false; status.setText("File saved"); });
                } catch (Exception e) { fail("Save failed: " + safeMessage(e)); }
                finally { file.delete(); }
            });
        }
    }

    private void openExternal(Uri uri) {
        String scheme = uri.getScheme();
        if (!"https".equals(scheme) && !"http".equals(scheme) && !"mailto".equals(scheme) && !"tel".equals(scheme)) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
        catch (ActivityNotFoundException e) { toast("No app can open this link."); }
    }
    private static String safeMessage(Exception e) {
        // Do not display provider paths, tokens, filenames or private server responses.
        if (e.getClass() == IOException.class && e.getMessage() != null) return e.getMessage();
        return "Connection or file access was interrupted.";
    }
    private void fail(String message) { runOnUiThread(() -> { if (!isDestroyed()) { busy = false; showError(message); } }); }
    private void showError(String message) {
        toolbar.setVisibility(View.GONE);
        new AlertDialog.Builder(this).setTitle("MedList").setMessage(message)
            .setPositiveButton("Retry", (dialog, which) -> {
                if (pendingShare != null && pendingShare.exists()) openPending(); else web.reload();
            }).setNegativeButton("Close", null).show();
    }
    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_LONG).show(); }
    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        web.saveState(state);
        if (pendingShare != null && (busy || (ShareUpload.ORIGIN + "/native-share").equals(web.getUrl()))) { state.putString("pendingShare", pendingShare.getName()); state.putString("pendingName", pendingName); }
    }
    @SuppressWarnings("deprecation")
    @Override public void onBackPressed() {
        if (busy) { toast("Please wait for the transfer to finish."); return; }
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        worker.shutdown();
        web.destroy();
        super.onDestroy();
    }
}
