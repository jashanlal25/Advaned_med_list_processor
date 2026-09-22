package com.medlist.nativeapp;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Locale;
import java.util.zip.GZIPInputStream;

/** Only app-owned HTML executes; attachment bytes stay base64 data until stored. */
final class LocalShare {
    static byte[] readDocument(File file) throws IOException {
        try (InputStream raw = new BufferedInputStream(new FileInputStream(file))) {
            raw.mark(2);
            int a = raw.read(), b = raw.read();
            raw.reset();
            InputStream input = a == 31 && b == 139 ? new GZIPInputStream(raw) : raw;
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            ShareUpload.copyLimited(input, bytes, ShareUpload.MAX_FILE_BYTES);
            if (bytes.size() == 0) throw new IOException("The shared document is empty.");
            return bytes.toByteArray();
        }
    }

    static String extension(String name, byte[] bytes) throws IOException {
        String lower = name.toLowerCase(Locale.ROOT);
        for (String ext : new String[]{".pdf", ".txt", ".html", ".htm"})
            if (lower.endsWith(ext)) return ext;
        String head = new String(bytes, 0, Math.min(4096, bytes.length), StandardCharsets.UTF_8)
            .replace("\ufeff", "").trim().toLowerCase(Locale.ROOT);
        if (head.startsWith("%pdf-")) return ".pdf";
        if (head.startsWith("<!doctype html") || head.substring(0, Math.min(1024, head.length())).contains("<html")) return ".htm";
        if (!head.isEmpty() && head.indexOf('\ufffd') < 0 && !head.matches("(?s).*[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f].*")) return ".txt";
        throw new IOException("Unsupported document. Share an HTML, TXT or PDF file.");
    }

    static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 32 || c == '<' || c == '>' || c == '&' || c == '\u2028' || c == '\u2029')
                out.append(String.format(Locale.ROOT, "\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }

    static String render(String template, String filename, byte[] bytes) throws IOException {
        String name = ShareUpload.safeName(filename);
        String ext = extension(name, bytes);
        if (!name.toLowerCase(Locale.ROOT).endsWith(ext)) name += ext;
        String type = ext.equals(".pdf") ? "PDF" : ext.equals(".txt") ? "TXT" : "HTML";
        String payload = "{\"filename\":" + quote(name) + ",\"ext\":" + quote(ext)
            + ",\"type\":" + quote(type) + ",\"size\":" + bytes.length
            + ",\"data_b64\":\"" + Base64.getEncoder().encodeToString(bytes) + "\"}";
        return template.replace("__MEDLIST_PAYLOAD__", payload);
    }
}
