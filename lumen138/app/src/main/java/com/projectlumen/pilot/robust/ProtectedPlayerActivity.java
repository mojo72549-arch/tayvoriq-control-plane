package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;

/** Final internal gate before the actual Media3 player is created. */
public final class ProtectedPlayerActivity extends Activity {
    static final String EXTRA_CHANNEL_ID = "parental_channel_id";
    static final String EXTRA_PARENTAL_REQUIRED = "parental_required";
    static final String EXTRA_PARENTAL_GRANT = "parental_grant";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        DiagnosticLog log = DiagnosticLog.get(this);
        String interaction = getIntent().getStringExtra(PlayerActivity.EXTRA_INTERACTION);
        String channelId = getIntent().getStringExtra(EXTRA_CHANNEL_ID);
        boolean required = getIntent().getBooleanExtra(EXTRA_PARENTAL_REQUIRED, false);
        String token = getIntent().getStringExtra(EXTRA_PARENTAL_GRANT);

        boolean allowed = !required
                || ParentalControl.consumePlaybackGrant(channelId, token);
        log.event(interaction, "PARENTAL-PLAYER-GATE",
                "required=" + required + " allowed=" + allowed
                        + " item=" + log.anonymousId(channelId));

        if (!allowed) {
            new AlertDialog.Builder(this)
                    .setTitle("Jugendschutz")
                    .setMessage("Dieser Inhalt ist gesperrt. Bitte über die Bibliothek mit der Eltern-PIN freigeben.")
                    .setCancelable(false)
                    .setPositiveButton("Zurück", (dialog, which) -> finish())
                    .show();
            return;
        }

        Intent player = new Intent(this, PlayerActivity.class);
        if (getIntent().getExtras() != null) player.putExtras(getIntent().getExtras());
        startActivity(player);
        finish();
    }
}
