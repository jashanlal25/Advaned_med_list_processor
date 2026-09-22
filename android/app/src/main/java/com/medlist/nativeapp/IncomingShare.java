package com.medlist.nativeapp;

import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Parcelable;
import java.util.*;

final class IncomingShare {
    static boolean isShare(Intent intent) {
        String action = intent.getAction();
        return Intent.ACTION_SEND.equals(action) || Intent.ACTION_SEND_MULTIPLE.equals(action)
            || Intent.ACTION_VIEW.equals(action);
    }

    @SuppressWarnings("deprecation")
    static List<Uri> files(Intent intent) {
        LinkedHashSet<Uri> files = new LinkedHashSet<>();
        if (Intent.ACTION_SEND_MULTIPLE.equals(intent.getAction())) {
            ArrayList<Parcelable> streams = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (streams != null) for (Parcelable stream : streams) if (stream instanceof Uri) add(files, (Uri) stream);
        } else {
            Parcelable stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (stream instanceof Uri) add(files, (Uri) stream);
        }
        ClipData clip = intent.getClipData();
        if (clip != null) for (int i = 0; i < clip.getItemCount(); i++) add(files, clip.getItemAt(i).getUri());
        if (Intent.ACTION_VIEW.equals(intent.getAction())) add(files, intent.getData());
        return new ArrayList<>(files);
    }

    private static void add(Set<Uri> files, Uri uri) {
        // Only read Android-granted content. Never treat share text or a URL as a file.
        if (uri != null && "content".equalsIgnoreCase(uri.getScheme())) files.add(uri);
    }
}
