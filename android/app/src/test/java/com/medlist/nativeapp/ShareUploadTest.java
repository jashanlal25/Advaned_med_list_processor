package com.medlist.nativeapp;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public class ShareUploadTest {
    @Test public void originIsExactAndHttpsOnly() {
        assertTrue(ShareUpload.isTrusted("https://medlist-new.vercel.app/make_html"));
        assertTrue(ShareUpload.isTrusted("https://medlist-new.vercel.app:443/"));
        assertFalse(ShareUpload.isTrusted("https://medlist-new.vercel.app.evil.example/"));
        assertFalse(ShareUpload.isTrusted("https://medlist-new.vercel.app@evil.example/"));
        assertFalse(ShareUpload.isTrusted("https://user@medlist-new.vercel.app/"));
        assertFalse(ShareUpload.isTrusted("http://medlist-new.vercel.app/"));
        assertFalse(ShareUpload.isTrusted("https://medlist-new.vercel.app:444/"));
        assertFalse(ShareUpload.isTrusted("file:///private/data"));
        assertFalse(ShareUpload.isTrusted(null));
    }
    @Test public void filenamesCannotInjectMultipartHeaders() {
        String header = new String(ShareUpload.prefix("boundary", "bad\"\r\nInjected: yes.htm"), StandardCharsets.UTF_8);
        assertFalse(header.contains("\r\nInjected"));
        assertTrue(header.contains("filename=\"bad___Injected: yes.htm\""));
        assertEquals("DOSANI MEDICOSE.HTM", ShareUpload.safeName("DOSANI MEDICOSE.HTM"));
        assertEquals("DOC-20260919-WA0011", ShareUpload.safeName("DOC-20260919-WA0011"));
        assertEquals("shared_document", ShareUpload.safeName(null));
    }
    @Test public void multipartPreservesEveryByte() throws Exception {
        byte[] document = new byte[3 * 1024 * 1024];
        for (int i = 0; i < document.length; i++) document[i] = (byte) (i % 256);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] prefix = ShareUpload.prefix("test-boundary", "example.HTM");
        output.write(prefix);
        assertEquals(document.length, ShareUpload.copyLimited(new ByteArrayInputStream(document), output, ShareUpload.MAX_FILE_BYTES));
        output.write(ShareUpload.suffix("test-boundary"));
        byte[] result = output.toByteArray();
        assertArrayEquals(document, java.util.Arrays.copyOfRange(result, prefix.length, prefix.length + document.length));
        assertTrue(new String(result, result.length - 21, 21, StandardCharsets.US_ASCII).endsWith("--test-boundary--\r\n"));
    }
    @Test public void overLimitFailsBeforeWritingExcess() throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try {
            ShareUpload.copyLimited(new ByteArrayInputStream(new byte[12]), output, 10);
            fail("Expected size check");
        } catch (IOException expected) { assertTrue(output.size() <= 10); }
    }
}
