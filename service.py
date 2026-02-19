# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, os, requests, json, re, time

# Updated for Translatarr
ADDON = xbmcaddon.Addon('service.translatarr')
DIALOG = xbmcgui.Dialog()

def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def notify(msg, title="Gemini Translator", duration=3000):
    DIALOG.notification(title, msg, xbmcgui.NOTIFICATION_INFO, duration)

def get_model_string():
    model_index = ADDON.getSetting('model') or "0"
    mapping = {"0": "gemini-2.0-flash", "1": "gemini-1.5-flash", "2": "gemini-2.5-flash"}
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    
    # Safely convert the text input to a float
    try:
        temp_input = ADDON.getSetting('temp')
        temp_val = float(temp_input) if temp_input else 0.15
        # Clamp value between 0.0 and 2.0 (Gemini limits)
        temp_val = max(0.0, min(temp_val, 2.0))
    except ValueError:
        log("Invalid temperature input, defaulting to 0.15")
        temp_val = 0.15

    log(f"AI Call: {model_name} | Applied Temp: {temp_val}")

    prefixed_lines = [f"L{i:03}: {text}" for i, text in enumerate(text_list)]
    input_text = "\n".join(prefixed_lines)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    prompt = (
        "### ROLE\nProfessional English-to-Romanian localizer.\n\n"
        "### RULES\n1. Translate line-by-line.\n2. Preserve 'Lxxx:' prefix.\n"
        f"3. Return exactly {expected_count} lines.\n4. Style: Natural Romanian."
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
        raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
        translated = [re.sub(r'^L\d{3}:\s*', '', l.strip()) for l in raw_output if re.match(r'^L\d{3}:', l.strip())]
        return translated if len(translated) == expected_count else None
    except Exception as e:
        log(f"API Error: {e}")
        return None

def process_subtitles(original_path):
    # Rule: Check if already translated
    if any(tag in original_path.lower() for tag in ['.ro.srt', '_ro.srt']): return
    
    save_dir = ADDON.getSetting('sub_folder')
    # CHANGED: Now saving as .ro.srt
    clean_name = os.path.basename(original_path).replace('.eng.srt', '.ro.srt').replace('.srt', '.ro.srt')
    save_path = os.path.join(save_dir, clean_name)

    if xbmcvfs.exists(save_path):
        log(f"Loading existing: {clean_name}")
        xbmc.Player().setSubtitles(save_path)
        return

    notify(f"Traducere pornită...")
    start_time = time.time()

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        
        if not blocks: return

        timestamps = [(b[0], b[1]) for b in blocks]
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        all_translated = []
        idx = 0
        chunk_size = 50 

        while idx < len(texts):
            if not xbmc.Player().isPlaying(): return
            curr_size = min(chunk_size, len(texts) - idx)
            res = translate_text_only(texts[idx:idx + curr_size], curr_size)
            if res:
                all_translated.extend(res)
                idx += curr_size
            else: return 

        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]
        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(final_srt))
        
        xbmc.Player().setSubtitles(save_path)
        duration = round(time.time() - start_time, 2)

        # --- THE CASSETTE BOX (Statistics) ---
        if ADDON.getSettingBool('show_stats'):

            stats_msg = (
                "✅ TRANSLATION FINISHED\n"
                "----------------------------------\n"
                f"📄 File: {clean_name}\n"
                f"🔢 Total Lines: {len(all_translated)}\n"
                f"⏱️ Duration: {duration}s\n"
                f"🧠 Model: {get_model_string()}\n"
                "----------------------------------\n"
                "Status: Romanian Subtitles Active"
            )
            # This opens the large text box "cassette"
            DIALOG.textviewer("Gemini Translation Stats", stats_msg)
        else:
            notify("Traducere finalizată!")

    except Exception as e: log(f"Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        custom_dir = ADDON.getSetting('sub_folder')
        if not custom_dir or not xbmcvfs.exists(custom_dir): return

        _, files = xbmcvfs.listdir(custom_dir)
        valid_files = [f for f in files if f.lower().endswith('.srt') and ".ro.srt" not in f.lower()]
        
        if valid_files:
            full_paths = [os.path.join(custom_dir, f) for f in valid_files]
            full_paths.sort(key=lambda x: xbmcvfs.Stat(x).st_mtime(), reverse=True)
            newest_path = full_paths[0]
            
            if newest_path != self.last_processed:
                stat = xbmcvfs.Stat(newest_path)
                if stat.st_size() > 1000 and (time.time() - stat.st_mtime() < 300):
                    self.last_processed = newest_path
                    process_subtitles(newest_path)

if __name__ == '__main__':
    import sys
    # If the script is run manually, sys.argv[0] is the script name.
    # We check if it's being run as a script (click) vs a service (boot).
    if len(sys.argv) > 0 and "service.py" in sys.argv[0]:
        # This forces the settings to open when you click the icon
        ADDON.openSettings()
    
    # Always start the background monitor
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10):
            break






