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
    void submit(List<Channel> values) { items = values == null ? Collections.emptyList() : values; notifyDataSetChanged(); }
    Channel item(int position) { return position >= 0 && position < items.size() ? items.get(position) : null; }
    @Override public int getCount() { return items.size(); }
    @Override public Object getItem(int position) { return item(position); }
    @Override public long getItemId(int position) { Channel c = item(position); return c == null ? position : c.id.hashCode(); }

    @Override public View getView(int position, View convertView, ViewGroup parent) {
        Holder holder;
        if (convertView == null) {
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(16), dp(11), dp(14), dp(11));
            GradientDrawable bg = new GradientDrawable();
            bg.setColor(0xFF102337); bg.setCornerRadius(dp(15)); bg.setStroke(dp(1), 0xFF284A62);
            row.setBackground(bg);
            LinearLayout labels = new LinearLayout(context); labels.setOrientation(LinearLayout.VERTICAL);
            TextView name = new TextView(context); name.setTextColor(Color.WHITE); name.setTextSize(16); name.setTypeface(Typeface.DEFAULT, Typeface.BOLD); name.setSingleLine(true);
            TextView group = new TextView(context); group.setTextColor(0xFFA8BDCC); group.setTextSize(12); group.setSingleLine(true);
            labels.addView(name); labels.addView(group);
            row.addView(labels, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
            TextView play = new TextView(context); play.setText("▶"); play.setTextColor(0xFF5EEAD4); play.setTextSize(22); play.setGravity(Gravity.CENTER);
            row.addView(play, new LinearLayout.LayoutParams(dp(48), dp(48)));
            holder = new Holder(name, group); row.setTag(holder); convertView = row;
        } else holder = (Holder) convertView.getTag();
        Channel channel = item(position);
        holder.name.setText(channel == null ? "" : channel.name);
        holder.group.setText(channel == null ? "" : channel.group + " · " + label(channel.type));
        return convertView;
    }

    private static String label(Channel.Type type) { return type == Channel.Type.MOVIE ? "Film" : type == Channel.Type.SERIES ? "Serie" : "Live-TV"; }
    private int dp(int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }
    private static final class Holder {
        final TextView name;
        final TextView group;
        Holder(TextView name, TextView group) { this.name = name; this.group = group; }
    }
}
