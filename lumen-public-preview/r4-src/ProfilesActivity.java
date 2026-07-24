package com.projectlumen.publicpreview;

import android.app.*;
import android.os.Bundle;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import android.graphics.Color;
import java.util.*;

/** D-pad and touch friendly local profile / PIN management. */
public final class ProfilesActivity extends Activity {
    private ProfileStore store;
    private LinearLayout list;
    private TextView activeLabel;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new ProfileStore(this);
        setTitle("Project Lumen · Profile & Jugendschutz");
        render();
    }

    private void render() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(24), dp(28), dp(40));
        root.setBackgroundColor(Color.rgb(7, 9, 14));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));

        root.addView(text("Profile", 34, Color.WHITE, true));
        activeLabel = text("", 18, Color.LTGRAY, false);
        root.addView(activeLabel, margin(0, 8, 0, 20));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        Button add = button("+ Profil");
        add.setOnClickListener(v -> createProfile());
        Button pin = button("PIN verwalten");
        pin.setOnClickListener(v -> managePin());
        actions.addView(add, weight());
        actions.addView(pin, weightWithLeft());
        root.addView(actions);

        TextView hint = text(
                "Fernbedienung: Mit dem Steuerkreuz navigieren, OK zum Auswählen. " +
                "Ein Kinderprofil blendet eindeutig nicht jugendfreie Bereiche lokal aus.",
                16, Color.LTGRAY, false);
        root.addView(hint, margin(0, 18, 0, 18));

        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        root.addView(list);
        setContentView(scroll);
        refreshList();
        add.requestFocus();
    }

    private void refreshList() {
        ProfileStore.Snapshot snapshot = store.load();
        ProfileStore.Profile active = snapshot.active();
        activeLabel.setText("Aktiv: " + (active == null ? "–" : active.name) +
                (active != null && active.isChild() ? " · Kinderprofil" : ""));
        list.removeAllViews();
        for (ProfileStore.Profile profile : snapshot.profiles) {
            list.addView(profileCard(profile, snapshot));
        }
    }

    private View profileCard(ProfileStore.Profile profile, ProfileStore.Snapshot snapshot) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(20), dp(16), dp(20), dp(16));
        card.setBackgroundColor(Color.rgb(25, 30, 41));

        String badge = profile.kind == ProfileStore.Kind.CHILD ? "Kinderprofil" : "Erwachsenenprofil";
        card.addView(text(profile.name + (profile.id.equals(snapshot.activeId) ? "  ✓" : ""),
                23, Color.WHITE, true));
        card.addView(text(badge + (profile.hasPin() ? " · PIN geschützt" : ""),
                16, Color.LTGRAY, false), margin(0, 4, 0, 12));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        Button activate = button(profile.id.equals(snapshot.activeId) ? "Aktiv" : "Auswählen");
        activate.setEnabled(!profile.id.equals(snapshot.activeId));
        activate.setOnClickListener(v -> activate(profile));
        row.addView(activate, weight());

        Button delete = button("Löschen");
        delete.setEnabled(snapshot.profiles.size() > 1);
        delete.setOnClickListener(v -> delete(profile));
        row.addView(delete, weightWithLeft());
        card.addView(row);
        return wrapCard(card);
    }

    private void activate(ProfileStore.Profile target) {
        ProfileStore.Profile current = store.load().active();
        if (current != null && current.isChild() && target.kind == ProfileStore.Kind.ADULT) {
            if (!target.hasPin()) {
                toast("Für den Wechsel aus dem Kinderprofil zuerst eine Erwachsenen-PIN setzen.");
                return;
            }
            askPin(target, () -> doActivate(target));
        } else {
            doActivate(target);
        }
    }

    private void doActivate(ProfileStore.Profile target) {
        try {
            store.setActive(target.id);
            refreshList();
            toast("Profil gewechselt: " + target.name);
        } catch (Exception e) {
            toast(e.getMessage());
        }
    }

    private void createProfile() {
        LinearLayout box = dialogBox();
        EditText name = input("Profilname", false);
        box.addView(name);
        Spinner kind = new Spinner(this);
        kind.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"Erwachsenenprofil", "Kinderprofil"}));
        box.addView(kind);

        new AlertDialog.Builder(this)
                .setTitle("Neues Profil")
                .setView(box)
                .setPositiveButton("Erstellen", (dialog, which) -> {
                    try {
                        store.create(name.getText().toString(),
                                kind.getSelectedItemPosition() == 1
                                        ? ProfileStore.Kind.CHILD
                                        : ProfileStore.Kind.ADULT);
                        refreshList();
                    } catch (Exception e) {
                        toast(e.getMessage());
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void managePin() {
        ProfileStore.Snapshot snapshot = store.load();
        List<ProfileStore.Profile> adults = new ArrayList<>();
        for (ProfileStore.Profile profile : snapshot.profiles) {
            if (profile.kind == ProfileStore.Kind.ADULT) adults.add(profile);
        }
        if (adults.isEmpty()) {
            toast("Kein Erwachsenenprofil vorhanden.");
            return;
        }
        String[] names = new String[adults.size()];
        for (int i = 0; i < adults.size(); i++) names[i] = adults.get(i).name;
        new AlertDialog.Builder(this)
                .setTitle("Erwachsenenprofil wählen")
                .setItems(names, (dialog, which) -> setPin(adults.get(which)))
                .show();
    }

    private void setPin(ProfileStore.Profile profile) {
        LinearLayout box = dialogBox();
        EditText first = input("Neue PIN (4–8 Ziffern)", true);
        EditText second = input("PIN wiederholen", true);
        box.addView(first);
        box.addView(second);

        new AlertDialog.Builder(this)
                .setTitle("PIN für " + profile.name)
                .setView(box)
                .setPositiveButton("Speichern", (dialog, which) -> {
                    String one = first.getText().toString();
                    String two = second.getText().toString();
                    if (!one.equals(two)) {
                        toast("Die PINs stimmen nicht überein.");
                        return;
                    }
                    try {
                        store.setPin(profile.id, one.toCharArray());
                        refreshList();
                        toast("PIN gespeichert.");
                    } catch (Exception e) {
                        toast(e.getMessage());
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void askPin(ProfileStore.Profile profile, Runnable success) {
        EditText pin = input("PIN", true);
        new AlertDialog.Builder(this)
                .setTitle("Jugendschutz-PIN")
                .setView(pin)
                .setPositiveButton("Freigeben", (dialog, which) -> {
                    if (store.verifyPin(profile.id, pin.getText().toString().toCharArray())) {
                        success.run();
                    } else {
                        toast("PIN ist falsch.");
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void delete(ProfileStore.Profile profile) {
        Runnable action = () -> {
            try {
                store.delete(profile.id);
                refreshList();
            } catch (Exception e) {
                toast(e.getMessage());
            }
        };
        if (profile.kind == ProfileStore.Kind.ADULT && profile.hasPin()) {
            askPin(profile, action);
        } else {
            new AlertDialog.Builder(this)
                    .setTitle("Profil löschen?")
                    .setMessage(profile.name)
                    .setPositiveButton("Löschen", (dialog, which) -> action.run())
                    .setNegativeButton("Abbrechen", null)
                    .show();
        }
    }

    private LinearLayout dialogBox() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(8), dp(24), 0);
        return box;
    }

    private EditText input(String hint, boolean pin) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setTextColor(Color.WHITE);
        field.setHintTextColor(Color.GRAY);
        field.setSingleLine(true);
        if (pin) {
            field.setInputType(InputType.TYPE_CLASS_NUMBER |
                    InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        }
        return field;
    }

    private Button button(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(17);
        button.setMinHeight(dp(56));
        button.setFocusable(true);
        button.setAllCaps(false);
        return button;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        if (bold) text.setTypeface(null, 1);
        return text;
    }

    private View wrapCard(View view) {
        FrameLayout wrapper = new FrameLayout(this);
        wrapper.setPadding(0, dp(8), 0, dp(8));
        wrapper.addView(view, new FrameLayout.LayoutParams(-1, -2));
        return wrapper;
    }

    private LinearLayout.LayoutParams weight() {
        return new LinearLayout.LayoutParams(0, -2, 1f);
    }

    private LinearLayout.LayoutParams weightWithLeft() {
        LinearLayout.LayoutParams params = weight();
        params.setMargins(dp(10), 0, 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams margin(int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void toast(String message) {
        Toast.makeText(this, message == null ? "Aktion fehlgeschlagen" : message,
                Toast.LENGTH_LONG).show();
    }
}
