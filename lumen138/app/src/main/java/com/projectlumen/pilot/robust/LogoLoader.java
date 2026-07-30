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
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Async playlist-logo loader with bounded memory/disk cache and recycled-view protection. */
final class LogoLoader {
    private static final int MAX_BYTES = 4 * 1024 * 1024;
    private static final int MAX_EDGE = 512;
    private static final long MAX_DISK = 32L * 1024L * 1024L;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService workers = Executors.newFixedThreadPool(3, runnable -> {
        Thread thread = new Thread(runnable, "lumen-logo-loader");
        thread.setDaemon(true);
        return thread;
    });
    private final LruCache<String, Bitmap> memory = new LruCache<String, Bitmap>(12 * 1024 * 1024) {
        @Override protected int sizeOf(String key, Bitmap value) {
            return value == null ? 0 : value.getAllocationByteCount();
        }
    };
    private final File cacheDir;

    LogoLoader(Context context) {
        cacheDir = new File(context.getCacheDir(), "channel-logos-v1");
        if (!cacheDir.exists()) cacheDir.mkdirs();
        workers.execute(this::trimDisk);
    }

    void load(String rawUrl, ImageView image, TextView fallback) {
        String url = rawUrl == null ? "" : rawUrl.trim();
        image.setTag(url);
        image.setImageDrawable(null);
        image.setVisibility(View.GONE);
        fallback.setVisibility(View.VISIBLE);
        if (!isSupported(url)) return;

        Bitmap cached = memory.get(url);
        if (cached != null && !cached.isRecycled()) {
            show(url, cached, image, fallback);
            return;
        }

        workers.execute(() -> {
            Bitmap bitmap = readDisk(url);
            if (bitmap == null) bitmap = download(url);
            if (bitmap != null) memory.put(url, bitmap);
            Bitmap result = bitmap;
            main.post(() -> {
                if (result != null) show(url, result, image, fallback);
            });
        });
    }

    void shutdown() { workers.shutdownNow(); }

    private void show(String url, Bitmap bitmap, ImageView image, TextView fallback) {
        if (!url.equals(image.getTag())) return;
        image.setImageBitmap(bitmap);
        image.setVisibility(View.VISIBLE);
        fallback.setVisibility(View.GONE);
    }

    private Bitmap readDisk(String url) {
        File file = fileFor(url);
        if (!file.isFile() || file.length() <= 0 || file.length() > MAX_BYTES) return null;
        try (InputStream input = new FileInputStream(file)) {
            Bitmap bitmap = BitmapFactory.decodeStream(input);
            if (bitmap == null) {
                file.delete();
                return null;
            }
            file.setLastModified(System.currentTimeMillis());
            return scale(bitmap);
        } catch (Exception ignored) {
            file.delete();
            return null;
        }
    }

    private Bitmap download(String value) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(value).openConnection();
            connection.setConnectTimeout(4_000);
            connection.setReadTimeout(7_000);
            connection.setInstanceFollowRedirects(true);
            connection.setRequestProperty("User-Agent", "Project-Lumen/13.2");
            connection.setRequestProperty("Accept", "image/*");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300 || connection.getContentLength() > MAX_BYTES) return null;
            byte[] data;
            try (InputStream input = connection.getInputStream();
                 ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[16_384];
                int total = 0;
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    total += count;
                    if (total > MAX_BYTES) return null;
                    output.write(buffer, 0, count);
                }
                data = output.toByteArray();
            }
            Bitmap bitmap = BitmapFactory.decodeByteArray(data, 0, data.length);
            if (bitmap == null) return null;
            Bitmap scaled = scale(bitmap);
            writeDisk(value, scaled);
            return scaled;
        } catch (Exception ignored) {
            return null;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private Bitmap scale(Bitmap source) {
        if (source == null) return null;
        int width = source.getWidth();
        int height = source.getHeight();
        if (width <= MAX_EDGE && height <= MAX_EDGE) return source;
        float factor = Math.min((float) MAX_EDGE / width, (float) MAX_EDGE / height);
        Bitmap scaled = Bitmap.createScaledBitmap(source,
                Math.max(1, Math.round(width * factor)),
                Math.max(1, Math.round(height * factor)), true);
        if (scaled != source) source.recycle();
        return scaled;
    }

    private void writeDisk(String url, Bitmap bitmap) {
        File target = fileFor(url);
        File temp = new File(target.getAbsolutePath() + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temp)) {
            if (bitmap.compress(Bitmap.CompressFormat.PNG, 92, output)) {
                if (target.exists()) target.delete();
                temp.renameTo(target);
            }
        } catch (Exception ignored) {
            temp.delete();
        }
    }

    private void trimDisk() {
        File[] files = cacheDir.listFiles();
        if (files == null) return;
        long total = 0;
        for (File file : files) total += Math.max(0, file.length());
        if (total <= MAX_DISK) return;
        java.util.Arrays.sort(files, java.util.Comparator.comparingLong(File::lastModified));
        for (File file : files) {
            long size = Math.max(0, file.length());
            if (file.delete()) total -= size;
            if (total <= MAX_DISK * 3 / 4) break;
        }
    }

    private File fileFor(String url) { return new File(cacheDir, digest(url) + ".img"); }

    private static boolean isSupported(String url) {
        return url.startsWith("http://") || url.startsWith("https://");
    }

    private static String digest(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (int index = 0; index < 16; index++) {
                out.append(String.format(Locale.ROOT, "%02x", bytes[index]));
            }
            return out.toString();
        } catch (Exception ignored) {
            return Integer.toHexString(value.hashCode());
        }
    }
}
