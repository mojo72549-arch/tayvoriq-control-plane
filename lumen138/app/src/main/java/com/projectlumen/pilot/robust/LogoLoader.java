package com.projectlumen.pilot.robust;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.view.View;
import android.widget.ImageView;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Small fail-soft image loader. Logo failures never block or alter catalog rows. */
final class LogoLoader {
    private static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final int CONNECT_TIMEOUT_MS = 5_000;
    private static final int READ_TIMEOUT_MS = 8_000;
    private static volatile LogoLoader instance;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newFixedThreadPool(3, runnable -> {
        Thread thread = new Thread(runnable, "lumen-logo-loader");
        thread.setDaemon(true);
        return thread;
    });
    private final LruCache<String, Bitmap> memory = new LruCache<String, Bitmap>(12 * 1024) {
        @Override protected int sizeOf(String key, Bitmap value) {
            return Math.max(1, value.getByteCount() / 1024);
        }
    };
    private final File directory;

    static LogoLoader get(Context context) {
        LogoLoader value = instance;
        if (value != null) return value;
        synchronized (LogoLoader.class) {
            value = instance;
            if (value == null) instance = value = new LogoLoader(context.getApplicationContext());
            return value;
        }
    }

    private LogoLoader(Context context) {
        directory = new File(context.getCacheDir(), "station-logos-v1");
        if (!directory.exists()) directory.mkdirs();
    }

    void load(String logoUrl, ImageView image, TextView fallback) {
        String url = logoUrl == null ? "" : logoUrl.trim();
        image.setTag(url);
        image.setImageDrawable(null);
        image.setVisibility(View.INVISIBLE);
        fallback.setVisibility(View.VISIBLE);
        if (!isHttp(url)) return;

        Bitmap cached = memory.get(url);
        if (cached != null) {
            showIfCurrent(url, image, fallback, cached);
            return;
        }

        worker.execute(() -> {
            Bitmap bitmap = null;
            File file = new File(directory, key(url) + ".img");
            try {
                if (file.exists() && file.length() > 0 && file.length() <= MAX_BYTES) {
                    try (InputStream input = new FileInputStream(file)) {
                        bitmap = BitmapFactory.decodeStream(input);
                    }
                }
                if (bitmap == null) {
                    byte[] bytes = download(url);
                    bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
                    if (bitmap != null) writeAtomic(file, bytes);
                }
                if (bitmap != null) memory.put(url, bitmap);
            } catch (Throwable ignored) {
                if (file.exists() && file.length() == 0) file.delete();
            }
            Bitmap result = bitmap;
            main.post(() -> showIfCurrent(url, image, fallback, result));
        });
    }

    private void showIfCurrent(String url, ImageView image, TextView fallback, Bitmap bitmap) {
        Object tag = image.getTag();
        if (!(tag instanceof String) || !url.equals(tag)) return;
        if (bitmap == null) {
            image.setVisibility(View.INVISIBLE);
            fallback.setVisibility(View.VISIBLE);
            return;
        }
        image.setImageBitmap(bitmap);
        image.setVisibility(View.VISIBLE);
        fallback.setVisibility(View.INVISIBLE);
    }

    private static byte[] download(String value) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(value).openConnection();
        connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.45");
        connection.setRequestProperty("Accept", "image/*,*/*;q=0.5");
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("Logo HTTP " + status);
            int declared = connection.getContentLength();
            if (declared > MAX_BYTES) throw new IllegalStateException("Logo zu groß");
            try (InputStream input = connection.getInputStream();
                 ByteArrayOutputStream output = new ByteArrayOutputStream(
                         declared > 0 ? Math.min(declared, MAX_BYTES) : 32 * 1024)) {
                byte[] buffer = new byte[16 * 1024];
                int total = 0;
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    total += read;
                    if (total > MAX_BYTES) throw new IllegalStateException("Logo zu groß");
                    output.write(buffer, 0, read);
                }
                return output.toByteArray();
            }
        } finally {
            connection.disconnect();
        }
    }

    private static void writeAtomic(File target, byte[] bytes) throws Exception {
        File temp = new File(target.getParentFile(), target.getName() + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temp)) {
            output.write(bytes);
            output.flush();
            output.getFD().sync();
        }
        if (target.exists()) target.delete();
        if (!temp.renameTo(target)) temp.delete();
    }

    private static boolean isHttp(String value) {
        return value.startsWith("http://") || value.startsWith("https://");
    }

    private static String key(String value) {
        long hash = 0xcbf29ce484222325L;
        for (int i = 0; i < value.length(); i++) {
            hash ^= value.charAt(i);
            hash *= 0x100000001b3L;
        }
        return Long.toUnsignedString(hash, 16);
    }
}
