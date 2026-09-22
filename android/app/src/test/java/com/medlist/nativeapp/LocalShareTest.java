package com.medlist.nativeapp;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.GZIPOutputStream;

public class LocalShareTest {
    @Test public void renamedHtmlAndPdfAreRecognized() throws Exception {
        assertEquals(".htm", LocalShare.extension("DOC-123", "\ufeff <html>medicine</html>".getBytes(StandardCharsets.UTF_8)));
        assertEquals(".pdf", LocalShare.extension("DOC-123", "%PDF-1.7".getBytes(StandardCharsets.UTF_8)));
        assertEquals(".txt", LocalShare.extension("DOC-123", "Medicine 100\n".getBytes(StandardCharsets.UTF_8)));
    }
    @Test public void binaryIsRejected() throws Exception {
        try { LocalShare.extension("unknown", new byte[]{0, 1, 2}); fail(); }
        catch (IOException expected) { assertTrue(expected.getMessage().contains("Unsupported")); }
    }
    @Test public void scriptClosingFilenameCannotBecomeMarkup() throws Exception {
        String html = LocalShare.render("<script type=\"application/json\">__MEDLIST_PAYLOAD__</script>",
            "<script>alert(1)</script>.htm", "<html></html>".getBytes(StandardCharsets.UTF_8));
        assertFalse(html.contains("<script>alert"));
        assertEquals(1, html.split("</script>", -1).length - 1);
        assertTrue(html.contains("\\u003c"));
    }
    @Test public void largeAttachmentRoundTripsWithoutChanges() throws Exception {
        byte[] bytes = new byte[3 * 1024 * 1024];
        for (int i=0;i<bytes.length;i++) bytes[i]=(byte)(i%256);
        String json=LocalShare.render("__MEDLIST_PAYLOAD__", "large.HTM", bytes);
        String b64=json.substring(json.indexOf("\"data_b64\":\"")+12, json.length()-2);
        assertArrayEquals(bytes, Base64.getDecoder().decode(b64));
    }
    @Test public void gzipAndEmptyFilesHandledLocally() throws Exception {
        File file=File.createTempFile("share-test", ".tmp");
        try {
            try { LocalShare.readDocument(file); fail(); } catch(IOException expected) {}
            byte[] data="<html>medicine</html>".getBytes(StandardCharsets.UTF_8);
            try(OutputStream out=new GZIPOutputStream(new FileOutputStream(file))) {out.write(data);}
            assertArrayEquals(data,LocalShare.readDocument(file));
        } finally {file.delete();}
    }
}
