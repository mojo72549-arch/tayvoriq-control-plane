package com.tayvoriq.addonmanager;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.AdSize;
import com.google.android.gms.ads.AdView;
import com.google.android.gms.ads.MobileAds;

public final class MainActivity extends Activity {
    private static final int PICK_FILE = 1600;

    private static final int BG = Color.rgb(5, 8, 18);
    private static final int SURFACE = Color.rgb(13, 19, 33);
    private static final int TEXT = Color.rgb(245, 248, 255);
    private static final int MUTED = Color.rgb(158, 169, 192);
    private static final int CYAN = Color.rgb(0, 222, 235);
    private static final int VIOLET = Color.rgb(119, 91, 255);

    private AdView adView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        MobileAds.initialize(this, ignored -> { });
        setContentView(buildScreen());
    }

    private ScrollView buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(24), dp(20), dp(28));
        scroll.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout hero = card();
        hero.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(hero, matchWrap());

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_launcher_foreground);
        logo.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        hero.addView(logo, new LinearLayout.LayoutParams(dp(138), dp(138)));

        TextView brand = text("TAYVORIQ", 30, TEXT, true);
        brand.setGravity(Gravity.CENTER);
        hero.addView(brand, matchWrap());

        TextView product = text("UNIVERSAL IMPORT", 12, CYAN, true);
        product.setGravity(Gravity.CENTER);
        product.setPadding(0, dp(4), 0, dp(14));
        hero.addView(product, matchWrap());

        TextView intro = text(
                "Minecraft Bedrock + Spaceflight Simulator. Dateien lokal prüfen, ZIP-Inhalte erkennen und an das passende Spiel übergeben.",
                15, MUTED, false);
        intro.setGravity(Gravity.CENTER);
        hero.addView(intro, matchWrap());

        TextView formats = text(
                ".mcaddon   •   .mcpack   •   .mcworld   •   .zip",
                13, TEXT, true);
        formats.setGravity(Gravity.CENTER);
        formats.setPadding(0, dp(16), 0, 0);
        hero.addView(formats, matchWrap());

        LinearLayout games = new LinearLayout(this);
        games.setOrientation(LinearLayout.VERTICAL);
        games.setPadding(dp(18), dp(18), dp(18), dp(18));
        games.setBackground(rounded(SURFACE, 22));
        LinearLayout.LayoutParams gamesParams = matchWrap();
        gamesParams.topMargin = dp(16);
        root.addView(games, gamesParams);

        games.addView(text("Automatische Erkennung", 18, TEXT, true), matchWrap());
        TextView gameInfo = text(
                "Minecraft: Bedrock-Packs/Welten werden direkt an Minecraft übergeben.\n\nSpaceflight Simulator: ZIPs mit Blueprint.txt/Version.txt werden erkannt. Beim ersten Import wählst du einmal den Blueprints-Ordner; danach kann TAYVORIQ dort automatisch ablegen und Spaceflight Simulator starten.",
                14, MUTED, false);
        gameInfo.setPadding(0, dp(10), 0, 0);
        games.addView(gameInfo, matchWrap());

        Button choose = new Button(this);
        choose.setText("DATEI AUSWÄHLEN");
        choose.setTextColor(Color.WHITE);
        choose.setTextSize(15);
        choose.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        choose.setMinHeight(dp(56));
        choose.setBackground(rounded(VIOLET, 18));
        choose.setOnClickListener(v -> chooseFile());
        LinearLayout.LayoutParams buttonParams = matchWrap();
        buttonParams.topMargin = dp(18);
        root.addView(choose, buttonParams);

        TextView tip = text(
                "Du kannst unterstützte Dateien auch direkt im Downloads-Ordner antippen und „Mit TAYVORIQ importieren“ wählen.",
                13, MUTED, false);
        tip.setGravity(Gravity.CENTER);
        tip.setPadding(dp(8), dp(14), dp(8), 0);
        root.addView(tip, matchWrap());

        adView = new AdView(this);
        adView.setAdSize(AdSize.BANNER);
        adView.setAdUnitId("ca-app-pub-3940256099942544/6300978111");
        LinearLayout adHost = new LinearLayout(this);
        adHost.setGravity(Gravity.CENTER);
        adHost.setPadding(0, dp(20), 0, 0);
        adHost.addView(adView, new LinearLayout.LayoutParams(dp(320), dp(50)));
        root.addView(adHost, matchWrap());
        adView.loadAd(new AdRequest.Builder().build());

        TextView disclaimer = text(
                "Unabhängiges Produkt. Nicht von Mojang, Microsoft oder Spaceflight Simulator UK Ltd genehmigt oder mit diesen verbunden.",
                11, MUTED, false);
        disclaimer.setGravity(Gravity.CENTER);
        disclaimer.setPadding(dp(10), dp(18), dp(10), 0);
        root.addView(disclaimer, matchWrap());

        return scroll;
    }

    private void chooseFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {
                "application/octet-stream",
                "application/zip",
                "application/x-zip-compressed",
                "application/mcaddon",
                "application/mcpack",
                "application/mcworld"
        });
        startActivityForResult(Intent.createChooser(intent, "Import-Datei auswählen"), PICK_FILE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_FILE || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        Uri uri = data.getData();
        Intent handoff = new Intent(this, FileImportActivity.class);
        handoff.setAction(Intent.ACTION_VIEW);
        handoff.setDataAndType(uri, data.getType() == null ? "application/octet-stream" : data.getType());
        handoff.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startActivity(handoff);
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(20), dp(20), dp(20), dp(20));
        card.setBackground(rounded(SURFACE, 24));
        return card;
    }

    private TextView text(String value, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setLineSpacing(0f, 1.14f);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private GradientDrawable rounded(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        if (color == SURFACE) drawable.setStroke(dp(1), Color.rgb(40, 56, 83));
        return drawable;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        if (adView != null) adView.destroy();
        super.onDestroy();
    }
}
