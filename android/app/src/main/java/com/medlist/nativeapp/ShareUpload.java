package com.medlist.nativeapp;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Native multipart transport; never goes through Chrome or a service worker. */
final class ShareUpload {
    static final String ORIGIN = "https://medlist-new.vercel.app";
    static final int MAX_FILE_BYTES = 15 * 1024 * 1024; // Leave room in the server's 16 MiB request limit.
    static final int MAX_RESPONSE_BYTES = 24 * 1024 * 1024;

    static boolean isTrusted(String value) {
        try {
            URI uri = new URI(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                && "medlist-new.vercel.app".equalsIgnoreCase(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443)
                && uri.getRawUserInfo() == null;
        } catch (Exception e) { return false; }
    }

    static String safeName(String name) {
        if (name == null || name.trim().isEmpty()) return "shared_document";
        String safe = name.replaceAll("[\\p{Cntrl}\\\\/\"]", "_");
        // Keep a trailing extension when shortening a provider's oversized name.
        return safe.length() > 160 ? safe.substring(safe.length() - 160) : safe;
    }

    static byte[] prefix(String boundary, String name) {
        return ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"shared_file\"; filename=\""
            + safeName(name) + "\"\r\nContent-Type: application/octet-stream\r\n\r\n")
            .getBytes(StandardCharsets.UTF_8);
    }

    static byte[] suffix(String boundary) {
        return ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.US_ASCII);
    }

    static long copyLimited(InputStream input, OutputStream output, long limit) throws IOException {
        byte[] buffer = new byte[16384];
        long total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > limit) throw new IOException("File exceeds the supported size limit.");
            output.write(buffer, 0, count);
        }
        return total;
    }

    static final class Response {
        final String html;
        final List<String> cookies;
        Response(String html, List<String> cookies) { this.html = html; this.cookies = cookies; }
    }

    static Response upload(File file, String name, String cookie) throws IOException {
        String boundary = "MedList-" + UUID.randomUUID();
        byte[] prefix = prefix(boundary, name), suffix = suffix(boundary);
        HttpURLConnection connection = (HttpURLConnection) new URL(ORIGIN + "/share-target").openConnection();
        try {
            connection.setInstanceFollowRedirects(false); // Never forward private bytes to another host.
            connection.setConnectTimeout(20000);
            connection.setReadTimeout(90000);
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
            connection.setRequestProperty("Accept", "text/html");
            connection.setRequestProperty("X-Medlist-Share-Client", "android-native-1");
            if (cookie != null && !cookie.isEmpty()) connection.setRequestProperty("Cookie", cookie);
            connection.setFixedLengthStreamingMode(prefix.length + file.length() + suffix.length);
            try (OutputStream output = connection.getOutputStream(); InputStream input = new FileInputStream(file)) {
                output.write(prefix);
                copyLimited(input, output, MAX_FILE_BYTES);
                output.write(suffix);
            }
            int status = connection.getResponseCode();
            if (status == 413) throw new IOException("The hosting server rejected this file as too large (HTTP 413).");
            if (status != 200 && status != 400)
                throw new IOException("MedList returned HTTP " + status + ". Try again when the site is available.");
            String type = connection.getContentType();
            if (type == null || !type.toLowerCase(Locale.ROOT).startsWith("text/html"))
                throw new IOException("MedList returned an unexpected response. Please retry.");
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            try (InputStream input = status >= 400 ? connection.getErrorStream() : connection.getInputStream()) {
                if (input == null) throw new IOException("The server returned an empty response.");
                copyLimited(input, body, MAX_RESPONSE_BYTES);
            }
            List<String> cookies = new ArrayList<>();
            for (Map.Entry<String, List<String>> header : connection.getHeaderFields().entrySet()) {
                if ("Set-Cookie".equalsIgnoreCase(header.getKey())) cookies.addAll(header.getValue());
            }
            return new Response(body.toString(StandardCharsets.UTF_8.name()), cookies);
        } finally { connection.disconnect(); }
    }
}
