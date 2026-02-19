# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, os, requests, json, re, time

ADDON = xbmcaddon.Addon('service.translatarr')
DIALOG = xbmcgui.Dialog()

def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def notify(msg, title="Translatarr", duration=3000):
    DIALOG.notification(title, msg, xbmcgui.NOTIFICATION_INFO, duration)

def get_model_string():
    model_index = ADDON.getSetting('model') or "0"
    mapping = {"0": "gemini-2.0-flash", "1": "gemini-1.5-flash", "2": "gemini-2.5-flash"}
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    
    try:
        temp_val = float(ADDON.getSetting('temp') or 0.15)
    except:
        temp_val = 0.15

    # STRICT V2 LOGIC: Explicitly numbered lines
    input_text = "\n".join([f"L{i:03}: {text}" for i, text in enumerate(text_list)])
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    prompt = (
        "Translate the following English subtitles to Romanian. "
        "Keep the same number of lines. Preserve the 'Lxxx:' prefix at the start of each line. "
        "The output must contain exactly the same number of lines as the input."
    )

    try:
        payload = {
            "contents": [{"parts": [{"text": f"{prompt}\n\n{input_text}"}]}],
            "generationConfig": {"temperature": temp_val, "topP": 0.95}
        }
        r = requests.post(url, json=payload, timeout=30)
        res_json = r.json()
        
        if 'candidates' not in res_json: return None
            
        raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
        
        # STRICT V2 CLEANING: Extracting only what follows the prefix
        translated = []
        # Find all occurrences of L followed by digits, then colon, then the rest of the line
        pattern = re.compile(r'^L\d{3}:\s*(.*)$', re.MULTILINE)
        matches = pattern.findall(raw_text)
        
        if len(matches) >= expected_count:
            return matches[:expected_count]
        else:
            # Fallback if AI gets the prefix slightly wrong but line count is okay
            lines = raw_text.strip().split('\n')
            fallback = [re.sub(r'^L\d{1,4}:?\s*', '', l) for l in lines]
            return fallback[:expected_count] if len(fallback) >= expected_count else None
    except: return None

def process_subtitles(original_path):
    if ".ro.srt" in original_path.lower(): return
    
    save_dir = ADDON.getSetting('sub_folder')
    base_name = os.path.basename(original_path)
    clean_name = re.sub(r'\.(eng|en|ro)?\.srt$', '', base_name, flags=re.IGNORECASE) + ".ro.srt"
    save_path = os.path.join(save_dir, clean_name)

    if xbmcvfs.exists(save_path):
        xbmc.Player().setSubtitles(save_path)
        return

    # Notification Mode Check
    use_notifications = ADDON.getSettingBool('notify_mode')
    
    if not use_notifications:
        pDialog = xbmcgui.DialogProgress()
        pDialog.create('Translatarr', 'Inițializare...')
    else:
        notify(f"Traducere începută: {clean_name}")

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        
        if not blocks: return

        timestamps = [(b[0], b[1]) for b in blocks]
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        all_translated = []
        idx = 0

        try:
            chunk_size = int(ADDON.getSetting('chunk_size') or 50)
        except: chunk_size = 50

        while idx < len(texts):
            # Check for cancel or player stop
            if (not use_notifications and pDialog.iscanceled()) or not xbmc.Player().isPlaying():
                if not use_notifications: pDialog.close()
                return
            
            percent = int((idx / len(texts)) * 100)
            status_msg = f"Progres: {percent}% ({idx}/{len(texts)})"
            
            if not use_notifications:
                pDialog.update(percent, status_msg)
            else:
                if idx % (chunk_size * 2) == 0: # Notify every 2 chunks to avoid spam
                    notify(status_msg)

            curr_size = min(chunk_size, len(texts) - idx)
            res = translate_text_only(texts[idx:idx + curr_size], curr_size)
            if res:
                all_translated.extend(res)
                idx += curr_size
            else:
                if not use_notifications: pDialog.close()
                notify("Eroare la segmentul de traducere.")
                return 

        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]
        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(final_srt))
        
        xbmc.Player().setSubtitles(save_path)
        if not use_notifications: pDialog.close()

        if ADDON.getSettingBool('show_stats'):
            stats_msg = f"✅ Gata: {clean_name}\n🔢 Linii: {len(all_translated)}\n🌡️ Temp: {ADDON.getSetting('temp')}"
            DIALOG.textviewer("Translatarr Stats", stats_msg)
        else:
            notify("Traducere completă!")

    except Exception as e:
        log(f"Fail: {e}")
        if 'pDialog' in locals(): pDialog.close()

# (Rest of GeminiMonitor and __main__ block remains the same)
