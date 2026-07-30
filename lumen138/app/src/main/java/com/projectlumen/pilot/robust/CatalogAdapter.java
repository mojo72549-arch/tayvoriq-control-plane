package com.projectlumen.pilot.robust;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Collections;
import java.util.List;
import java.util.Locale;

/** Virtualized premium rows with playlist logos, favorites and recent tracking. */
final class CatalogAdapter extends BaseAdapter {
    private final Context context;
    private final LogoLoader logos;
    private final UserCollectionStore collections;
    private List<Channel> items = Collections.emptyList();

    CatalogAdapter(Context context) {
        this.context = context;
        this.logos = new LogoLoader(context.getApplicationContext());
        this.collections = UserCollectionStore.init(context);
    }

    void submit(List<Channel> values) {
        items = values == null ? Collections.emptyList() : values;
        notifyDataSetChanged();
    }

    void close() { logos.shutdown(); }

    Channel item(int position) {
        return position >= 0 && position < items.size() ? items.get(position) : null;
    }

    @Override public int getCount() { return items.size(); }
    @Override public Object getItem(int position) { return item(position); }
    @Override public long getItemId(int position) {
        Channel channel = item(position);
        return channel == null ? position : channel.id.hashCode();
    }

    @Override public View getView(int position, View convertView, ViewGroup parent) {
        Holder holder;
        if (convertView == null) {
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(10), dp(8), dp(9), dp(8));
            row.setBackground(roundRect(0xEC0C2030, 16, 0xFF244D64));
            row.setMinimumHeight(dp(74));

            FrameLayout logoHost = new FrameLayout(context);
            logoHost.setBackground(roundRect(0xFF071522, 13, 0xFF31566C));
            ImageView logoImage = new ImageView(context);
            logoImage.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
            logoImage.setPadding(dp(4), dp(4), dp(4), dp(4));
            logoHost.addView(logoImage, new FrameLayout.LayoutParams(-1, -1));
            TextView logoFallback = new TextView(context);
            logoFallback.setTextColor(Color.WHITE);
            logoFallback.setTextSize(11);
            logoFallback.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            logoFallback.setGravity(Gravity.CENTER);
            logoFallback.setMaxLines(2);
            logoFallback.setEllipsize(TextUtils.TruncateAt.END);
            logoHost.addView(logoFallback, new FrameLayout.LayoutParams(-1, -1));
            row.addView(logoHost, new LinearLayout.LayoutParams(dp(58), dp(54)));

            LinearLayout labels = new LinearLayout(context);
            labels.setOrientation(LinearLayout.VERTICAL);
            labels.setPadding(dp(11), 0, dp(6), 0);
            TextView name = new TextView(context);
            name.setTextColor(Color.WHITE);
            name.setTextSize(15);
            name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            name.setSingleLine(true);
            name.setEllipsize(TextUtils.TruncateAt.END);
            labels.addView(name);
            TextView group = new TextView(context);
            group.setTextColor(0xFFA8C0D0);
            group.setTextSize(11);
            group.setSingleLine(true);
            group.setEllipsize(TextUtils.TruncateAt.END);
            labels.addView(group);
            row.addView(labels, new LinearLayout.LayoutParams(0, -2, 1f));

            TextView favorite = new TextView(context);
            favorite.setTextColor(0xFFFFD166);
            favorite.setTextSize(24);
            favorite.setGravity(Gravity.CENTER);
            favorite.setFocusable(true);
            favorite.setContentDescription("Favorit umschalten");
            favorite.setBackground(roundRect(0x3317354A, 12, 0x00315A70));
            row.addView(favorite, new LinearLayout.LayoutParams(dp(46), dp(46)));

            TextView language = new TextView(context);
            language.setTextColor(0xFF07111E);
            language.setTextSize(10);
            language.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            language.setGravity(Gravity.CENTER);
            language.setBackground(roundRect(0xFF7DE8D8, 10, 0xFF7DE8D8));
            row.addView(language, new LinearLayout.LayoutParams(dp(38), dp(30)));

            TextView play = new TextView(context);
            play.setText("›");
            play.setTextColor(0xFF63E6D2);
            play.setTextSize(28);
            play.setGravity(Gravity.CENTER);
            row.addView(play, new LinearLayout.LayoutParams(dp(31), dp(42)));

            holder = new Holder(logoImage, logoFallback, name, group, language, favorite);
            row.setTag(holder);
            convertView = row;
        } else {
            holder = (Holder) convertView.getTag();
        }

        Channel channel = item(position);
        if (channel == null) {
            holder.logoFallback.setText("");
            holder.name.setText("");
            holder.group.setText("");
            holder.language.setText("");
            holder.favorite.setText("☆");
            holder.favorite.setTag(null);
            holder.logoImage.setImageDrawable(null);
        } else {
            Brand brand = Brand.of(channel.name);
            holder.logoFallback.setText(brand.label);
            holder.logoFallback.setBackground(roundRect(brand.fill, 13, brand.stroke));
            logos.load(channel.logoUrl, holder.logoImage, holder.logoFallback);
            holder.name.setText(channel.name);
            ProviderLanguage.Facet facet = ProviderLanguageCache.detect(channel);
            String languageLabel = facet == null ? MediaLanguage.shortLabel(channel) : facet.flag + " " + facet.label;
            holder.group.setText(channel.group + "  ·  " + typeLabel(channel.type));
            holder.language.setText(facet == null ? MediaLanguage.shortLabel(channel) : facet.flag);
            holder.language.setContentDescription(languageLabel);
            holder.favorite.setText(collections.isFavorite(channel) ? "★" : "☆");
            holder.favorite.setTag(channel);
            holder.favorite.setOnClickListener(view -> {
                Object tag = view.getTag();
                if (tag instanceof Channel) {
                    collections.toggleFavorite((Channel) tag);
                    notifyDataSetChanged();
                }
            });
            convertView.setOnTouchListener((view, event) -> {
                if (event.getActionMasked() == MotionEvent.ACTION_UP) collections.markRecent(channel);
                return false;
            });
            convertView.setOnKeyListener((view, keyCode, event) -> {
                if (event.getAction() == KeyEvent.ACTION_UP
                        && (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER)) {
                    collections.markRecent(channel);
                }
                return false;
            });
        }
        return convertView;
    }

    private static String typeLabel(Channel.Type type) {
        return type == Channel.Type.MOVIE ? "Film"
                : type == Channel.Type.SERIES ? "Serie" : "Live";
    }

    private GradientDrawable roundRect(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    private static final class Holder {
        final ImageView logoImage;
        final TextView logoFallback;
        final TextView name;
        final TextView group;
        final TextView language;
        final TextView favorite;

        Holder(ImageView logoImage, TextView logoFallback, TextView name,
               TextView group, TextView language, TextView favorite) {
            this.logoImage = logoImage;
            this.logoFallback = logoFallback;
            this.name = name;
            this.group = group;
            this.language = language;
            this.favorite = favorite;
        }
    }

    private static final class Brand {
        final String label;
        final int fill;
        final int stroke;

        Brand(String label, int fill, int stroke) {
            this.label = label;
            this.fill = fill;
            this.stroke = stroke;
        }

        static Brand of(String value) {
            String name = value == null ? "" : value.toLowerCase(Locale.ROOT);
            if (name.contains("kanal d")) return new Brand("KANAL\nD", 0xFF1478C9, 0xFF66B8F0);
            if (name.contains("trt 1") || name.startsWith("trt1")) return new Brand("TRT 1", 0xFFE2263E, 0xFFFF7486);
            if (name.startsWith("trt")) return new Brand("TRT", 0xFFE2263E, 0xFFFF7486);
            if (name.contains("rtl zwei") || name.contains("rtl2")) return new Brand("RTL\nZWEI", 0xFFF29F24, 0xFFFFCF6B);
            if (name.contains("rtl")) return new Brand("RTL", 0xFFE64167, 0xFFFF8EA6);
            if (name.contains("zdf")) return new Brand("ZDF", 0xFFF07B22, 0xFFFFB172);
            if (name.contains("ard") || name.contains("das erste")) return new Brand("ARD", 0xFF1677C8, 0xFF70B7EE);
            if (name.contains("show tv")) return new Brand("SHOW", 0xFF7B3FB5, 0xFFB98BE2);
            if (name.startsWith("atv") || name.contains(" atv")) return new Brand("atv", 0xFFE65C2A, 0xFFFFA27F);
            if (name.contains("tv8")) return new Brand("TV8", 0xFFE32936, 0xFFFF7F88);
            String clean = value == null ? "" : value.trim();
            String label = clean.isBlank() ? "LUMEN" : clean.substring(0, Math.min(8, clean.length())).toUpperCase(Locale.ROOT);
            return new Brand(label, 0xFF17384E, 0xFF4C7891);
        }
    }
}
