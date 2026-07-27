package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.SecureRandom;
import java.util.List;

import javax.crypto.Cipher;
import javax.crypto.CipherOutputStream;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class LegacyCandidateMigratorTest {
    @Test
    public void migratesLegacyAesGcmCandidateWithoutCipherInputStream() throws Exception {
        ByteArrayOutputStream playlist = new ByteArrayOutputStream(8 * 1024 * 1024);
        playlist.write("#EXTM3U\n".getBytes(StandardCharsets.UTF_8));
        for (int index = 0; index < 25_000; index++) {
            String group = index % 7 == 0 ? "Serien" : index % 4 == 0 ? "Filme" : "Live DE";
            String path = group.equals("Serien") ? "series"
                    : group.equals("Filme") ? "movie" : "live";
            String item = "#EXTINF:-1 group-title=\"" + group + "\",Legacy " + index + "\n"
                    + "https://example.test/" + path + "/" + index + ".ts\n";
            playlist.write(item.getBytes(StandardCharsets.UTF_8));
        }

        byte[] keyBytes = new byte[32];
        new SecureRandom().nextBytes(keyBytes);
        SecretKey key = new SecretKeySpec(keyBytes, "AES");
        File encrypted = Files.createTempFile("lumen-legacy-", ".enc").toFile();
        File plaintext = new File(encrypted.getParentFile(), encrypted.getName() + ".tmp");

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        byte[] iv = cipher.getIV();
        try (FileOutputStream file = new FileOutputStream(encrypted);
             BufferedOutputStream raw = new BufferedOutputStream(file, 1024 * 1024)) {
            raw.write(iv.length);
            raw.write(iv);
            try (CipherOutputStream output = new CipherOutputStream(raw, cipher)) {
                output.write(playlist.toByteArray());
            }
        }

        long started = System.nanoTime();
        List<Channel> channels = LegacyCandidateMigrator.migrate(
                encrypted,
                plaintext,
                key,
                100_000,
                30_000L,
                (stage, detail) -> { });
        long durationMs = (System.nanoTime() - started) / 1_000_000L;

        assertEquals(25_000, channels.size());
        assertEquals("Legacy 0", channels.get(0).name);
        assertEquals(Channel.Type.SERIES, channels.get(0).type);
        assertEquals(Channel.Type.MOVIE, channels.get(4).type);
        assertFalse("Klartext-Migrationsdatei muss gelöscht sein", plaintext.exists());
        assertTrue("Legacy migration took " + durationMs + " ms", durationMs < 30_000L);

        encrypted.delete();
    }
}
