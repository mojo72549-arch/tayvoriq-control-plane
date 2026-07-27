package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class MainActivity extends Activity {
    private static final int REQUEST_LOCAL = 8101;
    private enum Mode { LIVE, MOVIES, SERIES }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r, "lumen-catalog-worker"); t.setDaemon(true); return t; });
    private final AtomicInteger filterGeneration = new AtomicInteger();
    private DiagnosticLog log;
    private UiStallWatchdog watchdog;
    private PlaylistRepository repository;
    private List<Channel> all = Collections.emptyList();
    private CatalogAdapter adapter;
    private Mode mode = Mode.LIVE;
    private boolean busy = true;
    private long lastInputEvent;
    private TextView status;
    private TextView empty;
    private TextView count;
    private EditText search;
    private ListView list;
    private Button sourceButton;
    private Button liveButton;
    private Button movieButton;
    private Button seriesButton;
    private Runnable pendingFilter;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(0xFF07111E); getWindow().setNavigationBarColor(0xFF07111E);
        log = DiagnosticLog.get(this); watchdog = new UiStallWatchdog(log); repository = new PlaylistRepository(this);
        log.event("-", "APP-CREATE-START", "thread=" + Thread.currentThread().getName());
        buildUi();
        log.event("-", "APP-CREATE-END", "uiReady=true");
        restore();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(tv() ? 24 : 12), dp(tv() ? 18 : 10), dp(tv() ? 24 : 12), dp(10)); root.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{0xFF06101D,0xFF092233,0xFF10243A})); setContentView(root);
        LinearLayout header = new LinearLayout(this); header.setOrientation(LinearLayout.HORIZONTAL); header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout brand = new LinearLayout(this); brand.setOrientation(LinearLayout.VERTICAL); brand.addView(text("LUMEN FLOW", tv()?31:24, Color.WHITE, true)); brand.addView(text("Robust Import & Playback · " + BuildConfig.VERSION_NAME, tv()?14:11, 0xFFA7BED0, false)); header.addView(brand, new LinearLayout.LayoutParams(0,-2,1f));
        Button diag = button("Diagnose", false); diag.setOnClickListener(v -> startActivity(new Intent(this, DiagnosticsActivity.class))); header.addView(diag, new LinearLayout.LayoutParams(-2, dp(tv()?54:46)));
        sourceButton = button("Quelle +", true); sourceButton.setEnabled(false); sourceButton.setOnClickListener(v -> showSourceMenu()); LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(-2, dp(tv()?54:46)); sp.setMargins(dp(8),0,0,0); header.addView(sourceButton, sp); root.addView(header);
        LinearLayout modes = new LinearLayout(this); modes.setOrientation(LinearLayout.HORIZONTAL); modes.setPadding(0,dp(10),0,dp(8)); liveButton=modeButton("Live-TV",Mode.LIVE); movieButton=modeButton("Filme",Mode.MOVIES); seriesButton=modeButton("Serien",Mode.SERIES); modes.addView(liveButton,weighted(0)); modes.addView(movieButton,weighted(dp(7))); modes.addView(seriesButton,weighted(dp(7))); root.addView(modes);
        LinearLayout sb = new LinearLayout(this); sb.setOrientation(LinearLayout.HORIZONTAL); search = new EditText(this); search.setSingleLine(true); search.setHint("Sender, Film, Serie oder Gruppe suchen"); search.setTextColor(Color.WHITE); search.setHintTextColor(0xFF8DA5B8); search.setTextSize(tv()?18:15); search.setPadding(dp(14),dp(10),dp(14),dp(10)); search.setBackground(roundRect(0xFF102337,15,0xFF294A61)); search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int c,int a){} public void onTextChanged(CharSequence s,int st,int b,int c){scheduleFilter();} public void afterTextChanged(Editable e){}}); sb.addView(search,new LinearLayout.LayoutParams(0,dp(tv()?58:50),1f)); count=text("0",tv()?15:12,0xFF07111E,true); count.setGravity(Gravity.CENTER); count.setPadding(dp(12),0,dp(12),0); count.setBackground(roundRect(0xFF5EEAD4,20,0xFF5EEAD4)); LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-2,dp(tv()?48:42));cp.setMargins(dp(8),0,0,0);sb.addView(count,cp);root.addView(sb);
        FrameLayout host=new FrameLayout(this);LinearLayout.LayoutParams hp=new LinearLayout.LayoutParams(-1,0,1f);hp.setMargins(0,dp(8),0,dp(8));root.addView(host,hp);list=new ListView(this);list.setDivider(new ColorDrawable(Color.TRANSPARENT));list.setDividerHeight(dp(7));list.setFastScrollEnabled(true);list.setCacheColorHint(Color.TRANSPARENT);list.setSelector(roundRect(0x335EEAD4,16,0xFF5EEAD4));list.setOnItemClickListener((p,v,pos,id)->select(pos));host.addView(list,new FrameLayout.LayoutParams(-1,-1));empty=text("Bibliothek wird im Hintergrund vorbereitet …",tv()?19:15,0xFFB6C9D8,false);empty.setGravity(Gravity.CENTER);empty.setPadding(dp(24),dp(24),dp(24),dp(24));host.addView(empty,new FrameLayout.LayoutParams(-1,-1));list.setEmptyView(empty);adapter=new CatalogAdapter(this);list.setAdapter(adapter);
        status=text("Lokale Wiederherstellung wird gestartet …",tv()?14:12,0xFFA7BED0,false);status.setMaxLines(2);root.addView(status);updateModeStyles();
    }

    private void restore(){ setBusy(true,"Gespeicherte Bibliothek wird im Hintergrund wiederhergestellt …"); log.event("-","RESTORE-QUEUED","thread=background"); worker.execute(()->{long started=SystemClock.elapsedRealtime();try{List<Channel> restored=repository.restore((stage,detail)->log.event("-",stage,detail));main.post(()->{all=restored;setBusy(false,repository.sourceName()+" · "+all.size()+" Einträge bereit");empty.setText(all.isEmpty()?"Noch keine Quelle eingerichtet\n\nQuelle hinzufügen: Server + Login, Playlist-Link oder lokale M3U/M3U8-Datei.":"Keine Treffer im aktuellen Bereich.");filterNow();log.event("-","RESTORE-PARSE-END","entries="+all.size()+" durationMs="+(SystemClock.elapsedRealtime()-started));});}catch(Throwable f){log.exception("-","RESTORE-ERROR",f);main.post(()->{setBusy(false,"Wiederherstellung fehlgeschlagen. Du kannst eine Quelle neu hinzufügen.");empty.setText("Wiederherstellung fehlgeschlagen\n\nDiagnose öffnen oder Quelle neu hinzufügen.");});}}); }

    private void showSourceMenu(){ if(busy)return; new AlertDialog.Builder(this).setTitle("Quelle hinzufügen").setItems(new String[]{"Server + Login","Playlist-Link","Lokale M3U/M3U8-Datei"},(d,w)->{if(w==0)promptServer();else if(w==1)promptLink();else openLocal();}).setNegativeButton("Abbrechen",null).show(); }
    private void promptLink(){EditText name=input("Name der Quelle",false);name.setText("Meine Playlist");EditText url=input("Vollständiger M3U/M3U8-Link",false);url.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);new AlertDialog.Builder(this).setTitle("Playlist-Link").setMessage("Download, Verschlüsselung und Prüfung laufen im Hintergrund. Die bisherige Bibliothek bleibt bis zum vollständigen Erfolg aktiv.").setView(form(name,url)).setPositiveButton("Laden",(d,w)->{try{importUrl(name.getText().toString(),requireHttpUrl(url.getText().toString()),"PLAYLIST-LINK");}catch(Throwable f){validation(f);}}).setNegativeButton("Abbrechen",null).show();}
    private void promptServer(){EditText name=input("Name der Quelle",false);name.setText("Mein Server");EditText server=input("Serveradresse, z. B. http://server:8080",false);EditText user=input("Benutzername",false);EditText pass=input("Passwort",true);new AlertDialog.Builder(this).setTitle("Server + Login").setMessage("Lumen erstellt die Playlist-Adresse lokal. Zugangsdaten werden nicht in der Diagnose angezeigt.").setView(form(name,server,user,pass)).setPositiveButton("Verbinden",(d,w)->{try{String base=requireHttpUrl(server.getText().toString());while(base.endsWith("/"))base=base.substring(0,base.length()-1);String u=user.getText().toString().trim(),p=pass.getText().toString();if(u.isBlank()||p.isBlank())throw new IllegalArgumentException("Benutzername oder Passwort fehlt.");String url=base+"/get.php?username="+URLEncoder.encode(u,StandardCharsets.UTF_8.name())+"&password="+URLEncoder.encode(p,StandardCharsets.UTF_8.name())+"&type=m3u_plus&output=mpegts";importUrl(name.getText().toString(),url,"SERVER-LOGIN");}catch(Throwable f){validation(f);}}).setNegativeButton("Abbrechen",null).show();}
    private void openLocal(){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"audio/x-mpegurl","application/x-mpegurl","application/vnd.apple.mpegurl","text/plain","application/octet-stream"});startActivityForResult(i,REQUEST_LOCAL);}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode!=REQUEST_LOCAL||resultCode!=RESULT_OK||data==null||data.getData()==null)return;Uri uri=data.getData();try{getContentResolver().takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION);}catch(Throwable ignored){}importLocal(uri);}

    private void importUrl(String name,String url,String origin){String interaction=log.newInteractionId();setBusy(true,"Quelle wird heruntergeladen, verschlüsselt und geprüft …");log.event(interaction,"IMPORT-START","origin="+origin+" urlPresent=true");worker.execute(()->{try{List<Channel> result=repository.importUrl(name,url,(stage,detail)->log.event(interaction,stage,detail));main.post(()->finishImport(interaction,result));}catch(Throwable f){log.exception(interaction,"IMPORT-ERROR",f);main.post(()->importFailure(f));}});}
    private void importLocal(Uri uri){String interaction=log.newInteractionId();setBusy(true,"Lokale Datei wird verschlüsselt und geprüft …");log.event(interaction,"LOCAL-IMPORT-START","uriPresent=true");worker.execute(()->{try{List<Channel> result=repository.importUri("Lokale Playlist",getContentResolver(),uri,(stage,detail)->log.event(interaction,stage,detail));main.post(()->finishImport(interaction,result));}catch(Throwable f){log.exception(interaction,"LOCAL-IMPORT-ERROR",f);main.post(()->importFailure(f));}});}
    private void finishImport(String interaction,List<Channel> result){all=result;search.setText("");mode=Mode.LIVE;updateModeStyles();setBusy(false,repository.sourceName()+" · "+all.size()+" Einträge importiert");empty.setText("Keine Treffer im aktuellen Bereich.");filterNow();log.event(interaction,"CATALOG-READY","entries="+all.size());Toast.makeText(this,all.size()+" Einträge sind bereit.",Toast.LENGTH_LONG).show();}
    private void importFailure(Throwable f){setBusy(false,"Import fehlgeschlagen: "+message(f)+" · bisherige Bibliothek bleibt aktiv");Toast.makeText(this,"Import fehlgeschlagen. Diagnose öffnen; die bisherige Bibliothek wurde nicht ersetzt.",Toast.LENGTH_LONG).show();}

    private void select(int position){Channel c=adapter.item(position);if(c==null)return;String interaction=log.newInteractionId();long delay=lastInputEvent<=0?0:Math.max(0,SystemClock.uptimeMillis()-lastInputEvent);log.event(interaction,"INPUT-DELIVERED","deliveryDelayMs="+delay+" position="+position);log.event(interaction,"SELECTION-VALIDATE-START","item="+log.anonymousId(c.id));if(c.url.isBlank()){log.event(interaction,"SELECTION-INVALID","reason=empty-url");Toast.makeText(this,"Dieser Eintrag enthält keine Stream-Adresse.",Toast.LENGTH_LONG).show();return;}log.event(interaction,"SELECTION-VALIDATE-OK","type="+c.type);log.event(interaction,"PLAYER-NAV-REQUEST","item="+log.anonymousId(c.id));Intent i=new Intent(this,PlayerActivity.class);i.putExtra(PlayerActivity.EXTRA_URL,c.url);i.putExtra(PlayerActivity.EXTRA_NAME,c.name);i.putExtra(PlayerActivity.EXTRA_INTERACTION,interaction);startActivity(i);}

    private Button modeButton(String label,Mode target){Button b=button(label,false);b.setOnClickListener(v->{mode=target;search.setText("");updateModeStyles();filterNow();});return b;}
    private void updateModeStyles(){style(liveButton,mode==Mode.LIVE);style(movieButton,mode==Mode.MOVIES);style(seriesButton,mode==Mode.SERIES);}
    private void style(Button b,boolean selected){if(b==null)return;b.setTextColor(selected?0xFF07111E:Color.WHITE);b.setBackground(roundRect(selected?0xFF5EEAD4:0xFF17354A,14,selected?0xFF5EEAD4:0xFF2A5068));}
    private void scheduleFilter(){if(pendingFilter!=null)main.removeCallbacks(pendingFilter);pendingFilter=this::filterNow;main.postDelayed(pendingFilter,220);}
    private void filterNow(){if(pendingFilter!=null)main.removeCallbacks(pendingFilter);pendingFilter=null;int generation=filterGeneration.incrementAndGet();Mode wanted=mode;String query=search.getText().toString().trim().toLowerCase(Locale.ROOT);List<Channel> base=all;log.event("-","LIST-SNAPSHOT-REQUEST","mode="+wanted+" base="+base.size()+" queryLength="+query.length());worker.execute(()->{long started=SystemClock.elapsedRealtime();ArrayList<Channel> result=new ArrayList<>();for(Channel c:base){if(!matchesMode(c,wanted))continue;if(!query.isBlank()&&!matches(c,query))continue;result.add(c);}List<Channel> immutable=Collections.unmodifiableList(result);long duration=SystemClock.elapsedRealtime()-started;main.post(()->{if(generation!=filterGeneration.get()||wanted!=mode)return;adapter.submit(immutable);count.setText(Integer.toString(immutable.size()));status.setText(repository.sourceName()+" · "+label(wanted)+" · "+immutable.size()+" Treffer");log.event("-","LIST-SNAPSHOT-READY","rows="+immutable.size()+" durationMs="+duration);list.post(()->log.event("-","LIST-FIRST-FRAME","visibleChildren="+list.getChildCount()));});});}
    private static boolean matchesMode(Channel c,Mode m){return m==Mode.LIVE?c.type==Channel.Type.LIVE:m==Mode.MOVIES?c.type==Channel.Type.MOVIE:c.type==Channel.Type.SERIES;}
    private static boolean matches(Channel c,String q){return c.name.toLowerCase(Locale.ROOT).contains(q)||c.group.toLowerCase(Locale.ROOT).contains(q);}
    private static String label(Mode m){return m==Mode.MOVIES?"Filme":m==Mode.SERIES?"Serien":"Live-TV";}
    private void setBusy(boolean value,String message){busy=value;sourceButton.setEnabled(!value);status.setText(message);}
    private void validation(Throwable f){log.exception("-","IMPORT-VALIDATION-ERROR",f);Toast.makeText(this,message(f),Toast.LENGTH_LONG).show();}
    private EditText input(String hint,boolean password){EditText e=new EditText(this);e.setSingleLine(true);e.setHint(hint);e.setTextColor(Color.WHITE);e.setHintTextColor(0xFF8DA5B8);e.setPadding(dp(12),dp(10),dp(12),dp(10));e.setBackground(roundRect(0xFF102337,12,0xFF294A61));if(password)e.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return e;}
    private LinearLayout form(EditText...fields){LinearLayout f=new LinearLayout(this);f.setOrientation(LinearLayout.VERTICAL);f.setPadding(dp(18),dp(8),dp(18),0);for(EditText e:fields){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(5),0,dp(5));f.addView(e,p);}return f;}
    private static String requireHttpUrl(String raw)throws Exception{String value=raw==null?"":raw.trim();if(value.isBlank())throw new IllegalArgumentException("Adresse fehlt.");URI uri=new URI(value);String scheme=uri.getScheme()==null?"":uri.getScheme().toLowerCase(Locale.ROOT);if(!scheme.equals("http")&&!scheme.equals("https"))throw new IllegalArgumentException("Nur HTTP- und HTTPS-Adressen werden unterstützt.");if(uri.getHost()==null&&uri.getAuthority()==null)throw new IllegalArgumentException("Serveradresse ist unvollständig.");return value;}
    private static String message(Throwable f){return f==null||f.getMessage()==null||f.getMessage().isBlank()?"Vorgang konnte nicht abgeschlossen werden.":f.getMessage();}
    @Override public boolean dispatchTouchEvent(MotionEvent event){if(event.getActionMasked()==MotionEvent.ACTION_DOWN){lastInputEvent=event.getEventTime();log.event("-","INPUT-DOWN","deliveryDelayMs="+Math.max(0,SystemClock.uptimeMillis()-event.getEventTime()));}return super.dispatchTouchEvent(event);}
    @Override protected void onDestroy(){watchdog.stop();worker.shutdownNow();super.onDestroy();}
    private boolean tv(){return (getResources().getConfiguration().uiMode&Configuration.UI_MODE_TYPE_MASK)==Configuration.UI_MODE_TYPE_TELEVISION;}
    private TextView text(String value,float size,int color,boolean bold){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);if(bold)t.setTypeface(null,android.graphics.Typeface.BOLD);return t;}
    private Button button(String value,boolean primary){Button b=new Button(this);b.setText(value);b.setTextColor(primary?0xFF07111E:Color.WHITE);b.setBackground(roundRect(primary?0xFF5EEAD4:0xFF17354A,14,primary?0xFF5EEAD4:0xFF2A5068));return b;}
    private LinearLayout.LayoutParams weighted(int left){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(tv()?56:48),1f);p.setMargins(left,0,0,0);return p;}
    private GradientDrawable roundRect(int color,int radius,int stroke){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));d.setStroke(dp(1),stroke);return d;}
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
}
