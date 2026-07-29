package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Parent-only review of provider group names and exact local safety overrides. */
public final class AdultCategoryManagerActivity extends Activity {
    private static final int BG = 0xFF050D18;
    private static final int CARD = 0xEE0B2030;
    private static final int STROKE = 0xFF2A5269;
    private static final int ACCENT = 0xFF62E7D3;
    private static final int VIOLET = 0xFF7555D9;
    private static final int DANGER = 0xFFE94D5F;
    private static final int TEXT_SECONDARY = 0xFF9DB6C8;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-adult-groups");
        thread.setDaemon(true);
        return thread;
    });

    private DiagnosticLog log;
    private GroupAdapter adapter;
    private EditText search;
    private TextView status;
    private TextView empty;
    private ProgressBar progress;
    private List<GroupSummary> allGroups = Collections.emptyList();
    private volatile boolean destroyed;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        log = DiagnosticLog.get(this);
        if (!ParentalControl.isUnlocked()) {
            Toast.makeText(this, "Elternzugang ist gesperrt.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        buildUi();
        loadGroups();
    }

    @Override protected void onResume() {
        super.onResume();
        if (!ParentalControl.isUnlocked()) finish();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        main.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        super.onDestroy();
    }

    private void buildUi() {
        FrameLayout stage = new FrameLayout(this);
        stage.setBackground(new LumenFlowDrawable());
        setContentView(stage);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(14), dp(12), dp(14), dp(10));
        stage.addView(root, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView logo = new TextView(this);
        logo.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
        logo.setContentDescription("Project Lumen Logo");
        header.addView(logo, new LinearLayout.LayoutParams(dp(42), dp(42)));

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(dp(10), 0, dp(6), 0);
        titles.addView(text("18+ KATEGORIEN", 20, Color.WHITE, true));
        TextView subtitle = text("ANBIETERGRUPPEN SICHER ZUORDNEN", 9,
                TEXT_SECONDARY, true);
        subtitle.setLetterSpacing(0.05f);
        titles.addView(subtitle);
        header.addView(titles, new LinearLayout.LayoutParams(0, -2, 1f));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        header.addView(back, new LinearLayout.LayoutParams(dp(84), dp(40)));
        root.addView(header);

        TextView explanation = text(
                "Manche Anbieter benennen Erwachsenenbereiche ohne XXX oder Adult. "
                        + "Hier kannst du eine komplette Anbietergruppe exakt als XXX/Erotik, "
                        + "FSK 18 oder Familieninhalt festlegen. Die Auswahl bleibt nur auf diesem Gerät.",
                12, 0xFFBDD0DC, false);
        explanation.setPadding(dp(12), dp(10), dp(12), dp(10));
        explanation.setBackground(roundRect(CARD, 14, STROKE));
        LinearLayout.LayoutParams explanationParams = new LinearLayout.LayoutParams(-1, -2);
        explanationParams.setMargins(0, dp(10), 0, dp(8));
        root.addView(explanation, explanationParams);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Kategorie suchen, z. B. 18, Night, VIP oder VOD");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7896AA);
        search.setTextSize(14);
        search.setPadding(dp(13), 0, dp(12), 0);
        search.setBackground(roundRect(CARD, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                filter();
            }
            @Override public void afterTextChanged(Editable editable) { }
        });
        root.addView(search, new LinearLayout.LayoutParams(-1, dp(46)));

        status = text("Anbietergruppen werden ermittelt …", 11, TEXT_SECONDARY, false);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.setMargins(0, dp(7), 0, dp(4));
        root.addView(status, statusParams);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        if (progress.getIndeterminateDrawable() != null) {
            progress.getIndeterminateDrawable().setTint(VIOLET);
        }
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(-1, 0, 1f);
        hostParams.setMargins(0, dp(8), 0, 0);
        root.addView(host, hostParams);

        ListView list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x337555D9, 16, VIOLET));
        adapter = new GroupAdapter();
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) ->
                chooseRule(adapter.item(position)));
        host.addView(list, new FrameLayout.LayoutParams(-1, -1));

        empty = text("Noch keine Kategorien geladen.", 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(dp(22), dp(22), dp(22), dp(22));
        host.addView(empty, new FrameLayout.LayoutParams(-1, -1));
        list.setEmptyView(empty);
    }

    private void loadGroups() {
        progress.setVisibility(View.VISIBLE);
        worker.execute(() -> {
            try {
                List<Channel> raw = CatalogSession.raw();
                if (raw.isEmpty()) {
                    PlaylistRepository repository = new PlaylistRepository(this);
                    repository.restore((stage, detail) ->
                            log.event("-", "GROUP-" + stage, detail));
                    raw = CatalogSession.raw();
                }
                List<GroupSummary> groups = summarize(raw);
                int autoProtected = 0;
                int manual = 0;
                for (GroupSummary group : groups) {
                    if (group.automaticClass != AdultContentPolicy.CLASS_SAFE) autoProtected++;
                    if (group.manualRule != AdultGroupPolicy.RULE_AUTO) manual++;
                }
                int finalAutoProtected = autoProtected;
                int finalManual = manual;
                main.post(() -> {
                    if (!alive()) return;
                    allGroups = groups;
                    progress.setVisibility(View.GONE);
                    status.setText(groups.size() + " Kategorien · " + finalAutoProtected
                            + " automatisch geschützt · " + finalManual + " manuell zugeordnet");
                    filter();
                });
                log.event("-", "ADULT-GROUPS-READY", "groups=" + groups.size()
                        + " automaticProtected=" + autoProtected + " manual=" + manual);
            } catch (Throwable failure) {
                log.exception("-", "ADULT-GROUPS-ERROR", failure);
                main.post(() -> {
                    if (!alive()) return;
                    progress.setVisibility(View.GONE);
                    status.setText("Kategorien konnten nicht geladen werden");
                    empty.setText("Bitte Systemdiagnose prüfen.");
                });
            }
        });
    }

    private List<GroupSummary> summarize(List<Channel> source) {
        LinkedHashMap<String, GroupSummary> groups = new LinkedHashMap<>();
        for (Channel channel : source) {
            if (channel == null) continue;
            String key = AdultGroupPolicy.normalize(channel.group);
            GroupSummary summary = groups.get(key);
            if (summary == null) {
                summary = new GroupSummary(channel.group, channel.automaticAdultClass,
                        AdultGroupPolicy.manualRule(channel.group));
                groups.put(key, summary);
            }
            summary.total++;
            if (channel.type == Channel.Type.MOVIE) summary.movies++;
            else if (channel.type == Channel.Type.SERIES) summary.series++;
            else summary.live++;
            summary.automaticClass = stronger(summary.automaticClass,
                    channel.automaticAdultClass);
        }

        ArrayList<GroupSummary> result = new ArrayList<>(groups.values());
        result.sort(Comparator
                .comparingInt(GroupSummary::sortRank)
                .thenComparing(group -> group.name.toLowerCase(Locale.ROOT)));
        return Collections.unmodifiableList(result);
    }

    private void filter() {
        if (adapter == null || search == null) return;
        String query = search.getText().toString().trim();
        if (query.isEmpty()) {
            adapter.submit(allGroups);
            empty.setText("Keine Anbietergruppen vorhanden.");
            return;
        }
        ArrayList<GroupSummary> result = new ArrayList<>();
        for (GroupSummary group : allGroups) {
            if (containsIgnoreCase(group.name, query)) result.add(group);
        }
        adapter.submit(Collections.unmodifiableList(result));
        empty.setText("Keine Kategorie mit diesem Suchbegriff gefunden.");
    }

    private void chooseRule(GroupSummary group) {
        if (group == null || !ParentalControl.isUnlocked()) return;
        String[] options = new String[]{
                "Automatisch erkennen",
                "XXX / Erotik – vollständig schützen",
                "FSK 18 – vollständig schützen",
                "Familieninhalt – ausdrücklich freigeben"
        };
        new AlertDialog.Builder(this)
                .setTitle(group.name)
                .setMessage(group.total + " Einträge · " + group.movies + " Filme · "
                        + group.series + " Serien · " + group.live + " Live")
                .setItems(options, (dialog, which) -> {
                    byte rule = which == 1 ? AdultContentPolicy.CLASS_EXPLICIT
                            : which == 2 ? AdultContentPolicy.CLASS_AGE_18
                            : which == 3 ? AdultContentPolicy.CLASS_SAFE
                            : AdultGroupPolicy.RULE_AUTO;
                    applyRule(group, rule);
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void applyRule(GroupSummary group, byte rule) {
        progress.setVisibility(View.VISIBLE);
        status.setText("Kategorie wird sicher neu zugeordnet …");
        worker.execute(() -> {
            try {
                AdultGroupPolicy.setRule(group.name, rule);
                CatalogSession.rebuildPolicies();
                List<GroupSummary> updated = summarize(CatalogSession.raw());
                log.event("-", "ADULT-GROUP-RULE-CHANGED",
                        "groupId=" + log.anonymousId(group.name) + " rule=" + rule
                                + " revision=" + AdultGroupPolicy.revision());
                main.post(() -> {
                    if (!alive()) return;
                    allGroups = updated;
                    progress.setVisibility(View.GONE);
                    status.setText("Kategorie gespeichert · Familien- und 18+-Katalog aktualisiert");
                    filter();
                    Toast.makeText(this, "Zuordnung wurde gespeichert.", Toast.LENGTH_SHORT).show();
                });
            } catch (Throwable failure) {
                log.exception("-", "ADULT-GROUP-RULE-ERROR", failure);
                main.post(() -> {
                    if (!alive()) return;
                    progress.setVisibility(View.GONE);
                    status.setText("Zuordnung konnte nicht gespeichert werden");
                });
            }
        });
    }

    private static byte stronger(byte left, byte right) {
        if (left == AdultContentPolicy.CLASS_EXPLICIT || left == AdultContentPolicy.CLASS_ADULT_BRAND
                || right == AdultContentPolicy.CLASS_EXPLICIT
                || right == AdultContentPolicy.CLASS_ADULT_BRAND) {
            return AdultContentPolicy.CLASS_EXPLICIT;
        }
        if (left == AdultContentPolicy.CLASS_AGE_18 || right == AdultContentPolicy.CLASS_AGE_18) {
            return AdultContentPolicy.CLASS_AGE_18;
        }
        return AdultContentPolicy.CLASS_SAFE;
    }

    private static boolean containsIgnoreCase(String value, String query) {
        if (value == null || query == null) return false;
        int limit = value.length() - query.length();
        for (int index = 0; index <= limit; index++) {
            if (value.regionMatches(true, index, query, 0, query.length())) return true;
        }
        return false;
    }

    private boolean alive() {
        return !destroyed && !isFinishing() && !isDestroyed();
    }

    private Button button(String label, boolean primary) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setTextSize(11);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(Color.WHITE);
        button.setMinHeight(0);
        button.setMinWidth(0);
        button.setBackground(roundRect(primary ? VIOLET : 0xFF17354A,
                12, primary ? VIOLET : STROKE));
        return button;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        if (bold) text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return text;
    }

    private GradientDrawable roundRect(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private final class GroupAdapter extends BaseAdapter {
        private List<GroupSummary> items = Collections.emptyList();

        void submit(List<GroupSummary> values) {
            items = values == null ? Collections.emptyList() : values;
            notifyDataSetChanged();
        }

        GroupSummary item(int position) {
            return position >= 0 && position < items.size() ? items.get(position) : null;
        }

        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int position) { return item(position); }
        @Override public long getItemId(int position) {
            GroupSummary group = item(position);
            return group == null ? position : AdultGroupPolicy.normalize(group.name).hashCode();
        }

        @Override public View getView(int position, View convertView, ViewGroup parent) {
            LinearLayout row;
            Holder holder;
            if (convertView == null) {
                row = new LinearLayout(AdultCategoryManagerActivity.this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                row.setGravity(Gravity.CENTER_VERTICAL);
                row.setPadding(dp(12), dp(9), dp(10), dp(9));
                row.setBackground(roundRect(CARD, 15, STROKE));

                LinearLayout labels = new LinearLayout(AdultCategoryManagerActivity.this);
                labels.setOrientation(LinearLayout.VERTICAL);
                TextView name = text("", 14, Color.WHITE, true);
                name.setSingleLine(true);
                name.setEllipsize(TextUtils.TruncateAt.END);
                labels.addView(name);
                TextView detail = text("", 10, TEXT_SECONDARY, false);
                detail.setSingleLine(true);
                detail.setEllipsize(TextUtils.TruncateAt.END);
                labels.addView(detail);
                row.addView(labels, new LinearLayout.LayoutParams(0, -2, 1f));

                TextView badge = text("AUTO", 9, Color.WHITE, true);
                badge.setGravity(Gravity.CENTER);
                badge.setPadding(dp(7), 0, dp(7), 0);
                row.addView(badge, new LinearLayout.LayoutParams(-2, dp(30)));
                holder = new Holder(name, detail, badge);
                row.setTag(holder);
                convertView = row;
            } else {
                holder = (Holder) convertView.getTag();
            }

            GroupSummary group = item(position);
            if (group != null) {
                holder.name.setText(group.name);
                holder.detail.setText(group.total + " Einträge · " + group.movies + " Filme · "
                        + group.series + " Serien · " + group.live + " Live");
                byte effective = group.manualRule == AdultGroupPolicy.RULE_AUTO
                        ? group.automaticClass : group.manualRule;
                String label = group.manualRule == AdultGroupPolicy.RULE_AUTO ? "AUTO" : "MANUELL";
                int fill = effective == AdultContentPolicy.CLASS_AGE_18 ? 0xFFB65A22
                        : AdultContentPolicy.isExplicitClass(effective) ? DANGER
                        : group.manualRule == AdultContentPolicy.CLASS_SAFE ? 0xFF288C73 : VIOLET;
                holder.badge.setText(label + "\n" + AdultContentPolicy.classLabel(effective));
                holder.badge.setBackground(roundRect(fill, 10, fill));
            }
            return convertView;
        }
    }

    private static final class Holder {
        final TextView name;
        final TextView detail;
        final TextView badge;

        Holder(TextView name, TextView detail, TextView badge) {
            this.name = name;
            this.detail = detail;
            this.badge = badge;
        }
    }

    private static final class GroupSummary {
        final String name;
        byte automaticClass;
        final byte manualRule;
        int total;
        int movies;
        int series;
        int live;

        GroupSummary(String name, byte automaticClass, byte manualRule) {
            this.name = name == null || name.isBlank() ? "Weitere" : name;
            this.automaticClass = automaticClass;
            this.manualRule = manualRule;
        }

        int sortRank() {
            if (manualRule != AdultGroupPolicy.RULE_AUTO) return 0;
            if (automaticClass != AdultContentPolicy.CLASS_SAFE) return 1;
            String lower = name.toLowerCase(Locale.ROOT);
            if (lower.contains("18") || lower.contains("night") || lower.contains("vip")
                    || lower.contains("hot") || lower.contains("private")
                    || lower.contains("uncut") || lower.contains("mature")
                    || lower.contains("red") || lower.contains("venus")) return 2;
            return 3;
        }
    }
}