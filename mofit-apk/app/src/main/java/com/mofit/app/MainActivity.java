package com.mofit.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Locale;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final int MIC_PERMISSION = 3101;
    private WebView webView;
    private SpeechRecognizer speechRecognizer;
    private Intent speechIntent;
    private TextToSpeech textToSpeech;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean voiceWanted = false;
    private boolean speechRunning = false;
    private boolean ttsReady = false;
    private boolean ttsSpeaking = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(android.graphics.Color.rgb(7,16,29));
        getWindow().setNavigationBarColor(android.graphics.Color.rgb(7,16,29));
        initTextToSpeech();
        webView = new WebView(this);
        webView.setBackgroundColor(android.graphics.Color.rgb(7,16,29));
        setContentView(webView);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setTextZoom(100);
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient(){
            @Override public void onPermissionRequest(final PermissionRequest request){
                runOnUiThread(() -> {
                    if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) request.grant(request.getResources());
                    else request.deny();
                });
            }
        });
        webView.addJavascriptInterface(new NativeVoiceBridge(),"NativeVoice");
        webView.addJavascriptInterface(new NativeCoachBridge(),"NativeCoach");
        webView.loadUrl("file:///android_asset/index.html");
    }

    private void initTextToSpeech(){
        textToSpeech=new TextToSpeech(this,status->{
            if(status!=TextToSpeech.SUCCESS){ttsReady=false;return;}
            int result=textToSpeech.setLanguage(Locale.GERMANY);
            if(result==TextToSpeech.LANG_MISSING_DATA||result==TextToSpeech.LANG_NOT_SUPPORTED) result=textToSpeech.setLanguage(Locale.GERMAN);
            ttsReady=result!=TextToSpeech.LANG_MISSING_DATA&&result!=TextToSpeech.LANG_NOT_SUPPORTED;
            textToSpeech.setSpeechRate(.96f);
            textToSpeech.setPitch(1f);
            textToSpeech.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
            textToSpeech.setOnUtteranceProgressListener(new UtteranceProgressListener(){
                @Override public void onStart(String id){ttsSpeaking=true;speechRunning=false;}
                @Override public void onDone(String id){ttsSpeaking=false;if(voiceWanted)scheduleRestart(260);}
                @Override public void onError(String id){ttsSpeaking=false;if(voiceWanted)scheduleRestart(350);}
            });
        });
    }

    private void speakInternal(String text,boolean flush){
        if(text==null||text.trim().isEmpty())return;
        runOnUiThread(()->{
            if(!ttsReady||textToSpeech==null)return;
            if(speechRecognizer!=null&&speechRunning){try{speechRecognizer.cancel();}catch(Exception ignored){}speechRunning=false;}
            ttsSpeaking=true;
            textToSpeech.speak(text,flush?TextToSpeech.QUEUE_FLUSH:TextToSpeech.QUEUE_ADD,null,"mofit-"+UUID.randomUUID());
        });
    }

    private void stopCoachInternal(){
        runOnUiThread(()->{
            if(textToSpeech!=null)try{textToSpeech.stop();}catch(Exception ignored){}
            ttsSpeaking=false;
            if(voiceWanted)scheduleRestart(220);
        });
    }

    private void createSpeechRecognizerIfNeeded(){
        if(speechRecognizer!=null)return;
        if(!SpeechRecognizer.isRecognitionAvailable(this)){sendVoiceError("Spracherkennung ist auf diesem Gerät nicht verfügbar.");return;}
        speechRecognizer=SpeechRecognizer.createSpeechRecognizer(this);
        speechIntent=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE,"de-DE");
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE,"de-DE");
        speechIntent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS,false);
        speechIntent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS,3);
        speechRecognizer.setRecognitionListener(new RecognitionListener(){
            @Override public void onReadyForSpeech(Bundle b){speechRunning=true;}
            @Override public void onBeginningOfSpeech(){}
            @Override public void onRmsChanged(float v){}
            @Override public void onBufferReceived(byte[] b){}
            @Override public void onEndOfSpeech(){speechRunning=false;}
            @Override public void onError(int error){
                speechRunning=false;
                if(!voiceWanted||ttsSpeaking)return;
                if(error==SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS){voiceWanted=false;sendVoiceError("Mikrofon-Berechtigung fehlt.");return;}
                scheduleRestart(error==SpeechRecognizer.ERROR_RECOGNIZER_BUSY?1000:420);
            }
            @Override public void onResults(Bundle results){
                speechRunning=false;
                ArrayList<String> list=results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                if(list!=null&&!list.isEmpty())sendVoiceResult(list.get(0));
                if(voiceWanted&&!ttsSpeaking)scheduleRestart(300);
            }
            @Override public void onPartialResults(Bundle b){}
            @Override public void onEvent(int t,Bundle b){}
        });
    }

    private void startVoiceInternal(){
        voiceWanted=true;
        if(ttsSpeaking){scheduleRestart(450);return;}
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},MIC_PERMISSION);return;}
        createSpeechRecognizerIfNeeded();
        if(speechRecognizer==null||speechRunning)return;
        try{speechRecognizer.startListening(speechIntent);speechRunning=true;}catch(Exception e){speechRunning=false;sendVoiceError("Sprachsteuerung konnte nicht gestartet werden.");scheduleRestart(900);}
    }

    private void stopVoiceInternal(){
        voiceWanted=false;
        handler.removeCallbacksAndMessages(null);
        if(speechRecognizer!=null){try{speechRecognizer.stopListening();}catch(Exception ignored){}try{speechRecognizer.cancel();}catch(Exception ignored){}}
        speechRunning=false;
    }

    private void scheduleRestart(long ms){
        if(!voiceWanted)return;
        handler.postDelayed(()->{if(voiceWanted&&!speechRunning&&!ttsSpeaking)startVoiceInternal();},ms);
    }

    private void sendVoiceResult(String text){
        if(webView==null)return;
        String js="window.onNativeVoiceResult&&window.onNativeVoiceResult("+JSONObject.quote(text)+");";
        runOnUiThread(()->webView.evaluateJavascript(js,null));
    }

    private void sendVoiceError(String text){
        if(webView==null)return;
        String js="window.onNativeVoiceError&&window.onNativeVoiceError("+JSONObject.quote(text)+");";
        runOnUiThread(()->webView.evaluateJavascript(js,null));
    }

    public class NativeVoiceBridge{
        @JavascriptInterface public boolean isAvailable(){return SpeechRecognizer.isRecognitionAvailable(MainActivity.this);}
        @JavascriptInterface public void startVoice(){runOnUiThread(()->startVoiceInternal());}
        @JavascriptInterface public void stopVoice(){runOnUiThread(()->stopVoiceInternal());}
    }

    public class NativeCoachBridge{
        @JavascriptInterface public void speak(String text,boolean flush){speakInternal(text,flush);}
        @JavascriptInterface public void stop(){stopCoachInternal();}
        @JavascriptInterface public boolean isAvailable(){return ttsReady;}
    }

    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] grantResults){
        super.onRequestPermissionsResult(requestCode,permissions,grantResults);
        if(requestCode==MIC_PERMISSION){
            if(grantResults.length>0&&grantResults[0]==PackageManager.PERMISSION_GRANTED)startVoiceInternal();
            else{voiceWanted=false;sendVoiceError("Mikrofon-Berechtigung wurde nicht erteilt. Touch-Steuerung bleibt verfügbar.");}
        }
    }

    @Override public void onBackPressed(){if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();}
    @Override protected void onPause(){super.onPause();stopVoiceInternal();if(webView!=null)webView.onPause();}
    @Override protected void onResume(){super.onResume();if(webView!=null)webView.onResume();}
    @Override protected void onDestroy(){
        voiceWanted=false;handler.removeCallbacksAndMessages(null);
        if(speechRecognizer!=null){try{speechRecognizer.destroy();}catch(Exception ignored){}speechRecognizer=null;}
        if(textToSpeech!=null){try{textToSpeech.stop();}catch(Exception ignored){}try{textToSpeech.shutdown();}catch(Exception ignored){}textToSpeech=null;}
        if(webView!=null){webView.removeJavascriptInterface("NativeVoice");webView.removeJavascriptInterface("NativeCoach");webView.destroy();webView=null;}
        super.onDestroy();
    }
}
