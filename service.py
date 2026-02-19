# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, os, requests, json, re, time

# Updated for Translatarr
ADDON = xbmcaddon.Addon('service.translatarr')
DIALOG = xbmcgui.Dialog()

def log(msg): 
    xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def notify(msg, title="Gemini Translator", duration=3000):
    DIALOG.notification(title, msg, xbmcgui.NOTIFICATION_INFO, duration)

def get_model_string():
    model_index = ADDON.getSetting('model') or "0"
    mapping = {"0": "gemini-2.0-flash", "1": "gemini-1.5-flash", "2": "gemini-2.5-flash"}
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    
    # Safely convert temperature text to float
    try:
        temp_input = ADDON.getSetting('temp')
        temp_val = float(temp_input) if temp_input else 0.15
        temp_val = max(0.0, min(temp_val, 2.0))
    except:
        temp_val = 0.15

    prefixed_lines = [f"L{i:03}: {text}" for i, text in enumerate(text_list)]
    input_text = "\n".join(prefixed_lines)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    prompt = (
        "### ROLE\nProfessional English-to-Romanian localizer.\n\n"
        "### RULES\n1. Translate line-by-line.\n2. Preserve 'Lxxx:' prefix.\n"
        f"3. Return exactly {expected_count} lines.\n4. Style: Natural Romanian.\n"
        "5. DO NOT omit the Lxxx: prefix on any line."
    )

    try:
        payload = {
            "contents": [{"parts": [{"text": f"{prompt}\n\n{input_text}"}]}],
            "generationConfig": {
                "temperature": temp_val,
                "topP": 0.95
            }
        }
        r = requests.post(url, json=payload, timeout=30)
        res_json = r.json()
        
        if 'candidates' not in res_json:
            log(f"API Error: {res_json}")
            return None
            
        raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
        
        # AGGRESSIVE REGEX: Removes 'L' + digits + optional colon + space
        translated = []
        for line in raw_output:
            clean_line = re.sub(r'^L\d+:?\s*', '', line.strip())
            translated.append(clean_line)
            
        return translated[:expected_count] if len(translated) >= expected_count else None
    except Exception as e:
        log(f"Request Fail: {e}")
        return None

def process_subtitles(original_path):
    # Rule: Check if already translated to avoid infinite loop
    if ".ro.srt" in original_path.lower(): return
    
    save_dir = ADDON.getSetting('sub_folder')
    if not save_dir: return

    # FIX: Clean filename to prevent .ro.ro.srt
    base_name = os.path.basename(original_path)
    clean_name = re.sub(r'\.(eng|en|ro)?\.srt$', '', base_name, flags=re.IGNORECASE) + ".ro.srt"
    save_path = os.path.join(save_dir, clean_name)

    if xbmcvfs.exists(save_path):
        log(f"File exists, loading: {clean_name}")
        xbmc.Player().setSubtitles(save_path)
        return

    # PROGRESS DIALOG
    pDialog = xbmcgui.DialogProgress()
    pDialog.create('Translatarr', 'Pregătire traducere...')

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        
        if not blocks: 
            pDialog.close()
            return

        timestamps = [(b[0], b[1]) for b in blocks]
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        all_translated = []
        idx = 0

        # FETCH DYNAMIC CHUNK SIZE
        try:
            chunk_input = ADDON.getSetting('chunk_size')
            chunk_size = int(chunk_input) if chunk_input else 50
            chunk_size = max(10, min(chunk_size, 150))
        except:
            chunk_size = 50

        log(f"Starting translation: {len(texts)} lines, Chunks: {chunk_size}, Temp: {ADDON.getSetting('temp')}")

        while idx < len(texts):
            if pDialog.iscanceled() or not xbmc.Player().isPlaying():
                pDialog.close()
                return
            
            percent = int((idx / len(texts)) * 100)
            pDialog.update(percent, f"Progres: {idx} / {len(texts)} linii\nChunk Size: {chunk_size}")

            curr_size = min(chunk_size, len(texts) - idx)
            res = translate_text_only(texts[idx:idx + curr_size], curr_size)
            if res:
                all_translated.extend(res)
                idx += curr_size
            else: 
                log("Translation failed at a specific chunk.")
                pDialog.close()
                notify("Traducerea a eșuat la un segment.")
                return 

        # Final Formatting
        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]
        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(final_srt))
        
        xbmc.Player().setSubtitles(save_path)
        pDialog.close()

        if ADDON.getSettingBool('show_stats'):
            stats_msg = (
                f"✅ Traducere Finalizată\n"
                f"📄 Fișier: {clean_name}\n"
                f"🔢 Total Linii: {len(all_translated)}\n"
                f"🧠 Model: {get_model_string()}\n"
                f"🌡️ Temp: {ADDON.getSetting('temp')}"
            )
            DIALOG.textviewer("Translatarr Stats", stats_msg)
        else:
            notify("Traducere finalizată!")

    except Exception as e: 
        log(f"General Error: {e}")
        if 'pDialog' in locals(): pDialog.close()

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        custom_dir = ADDON.getSetting('sub_folder')
        if not custom_dir or not xbmcvfs.exists(custom_dir): return

        _, files = xbmcvfs.listdir(custom_dir)
        # Search for .srt files that are NOT Romanian already
        valid_files = [f for f in files if f.lower().endswith('.srt') and ".ro.srt" not in f.lower()]
        
        if valid_files:
            full_paths = [os.path.join(custom_dir, f) for f in valid_files]
            # Process the newest file found
            full_paths.sort(key=lambda x: xbmcvfs.Stat(x).st_mtime(), reverse=True)
            newest_path = full_paths[0]
            
            if newest_path != self.last_processed:
                stat = xbmcvfs.Stat(newest_path)
                # Ensure it's a real file and recently created/modified
                if stat.st_size() > 500 and (time.time() - stat.st_mtime() < 180):
                    self.last_processed = newest_path
                    process_subtitles(newest_path)

if __name__ == '__main__':
    import sys
    # Handle Program Addon Click
    if len(sys.argv) > 0 and "service.py" in sys.argv[0]:
        ADDON.openSettings()
    
    # Service Loop
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
