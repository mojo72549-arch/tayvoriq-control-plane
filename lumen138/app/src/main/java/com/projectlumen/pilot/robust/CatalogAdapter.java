package com.projectlumen.pilot.robust;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Collections;
import java.util.List;

final class CatalogAdapter extends BaseAdapter {
    private final Context context;
    private List<Channel> items = Collections.emptyList();

    CatalogAdapter(Context context) { this.context = context; }

    void submit(List<Channel> values) {
        items = values == null ? Collections.emptyList() : values;
        notifyDataSetChanged();
    }

    Channel item(int position) {
        return position >= 0 && position < items.size() ? items.get(position) : null;
    }

    @Override public int getCount() { return items.size(); }
    @Override public Object getItem(int position) { return item(position); }
    @Override public long getItemId(int position) {
        Channel channel = item(position);
        return channel == null ? position : channel.id.hashCode();
    }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) {
        Holder holder;
        if (convertView == null) {
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(11), dp(8), dp(10), dp(8));
            row.setBackground(roundRect(0xE80D2233, 14, 0xFF24465B));

            TextView badge = new TextView(context);
            badge.setTextColor(0xFF06101D);
            badge.setTextSize(14);
            badge.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            badge.setGravity(Gravity.CENTER);
            badge.setBackground(roundRect(0xFF5EEAD4, 12, 0xFF5EEAD4));
            row.addView(badge, new LinearLayout.LayoutParams(dp(38), dp(38)));

            LinearLayout labels = new LinearLayout(context);
            labels.setOrientation(LinearLayout.VERTICAL);
            labels.setPadding(dp(11), 0, dp(8), 0);
            TextView name = new TextView(context);
            name.setTextColor(Color.WHITE);
            name.setTextSize(15);
            name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            name.setSingleLine(true);
            TextView group = new TextView(context);
            group.setTextColor(0xFF92A9BA);
            group.setTextSize(11);
            group.setSingleLine(true);
            labels.addView(name);
            labels.addView(group);
            row.addView(labels, new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

            TextView play = new TextView(context);
            play.setText("›");
            play.setTextColor(0xFF5EEAD4);
            play.setTextSize(28);
            play.setGravity(Gravity.CENTER);
            row.addView(play, new LinearLayout.LayoutParams(dp(34), dp(42)));

            holder = new Holder(badge, name, group);
            row.setTag(holder);
            convertView = row;
        } else {
            holder = (Holder) convertView.getTag();
        }

        Channel channel = item(position);
        if (channel == null) {
            holder.badge.setText("");
            holder.name.setText("");
            holder.group.setText("");
        } else {
            holder.badge.setText(initial(channel.name));
            holder.name.setText(channel.name);
            holder.group.setText(channel.group + "  ·  " + label(channel.type));
        }
        return convertView;
    }

    private static String initial(String value) {
        if (value == null || value.isBlank()) return "•";
        return value.substring(0, 1).toUpperCase();
    }

    private static String label(Channel.Type type) {
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
        final TextView badge;
        final TextView name;
        final TextView group;

        Holder(TextView badge, TextView name, TextView group) {
            this.badge = badge;
            this.name = name;
            this.group = group;
        }
    }
}
