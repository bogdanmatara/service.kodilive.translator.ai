# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, os, requests, json, re, time

ADDON = xbmcaddon.Addon()
DIALOG = xbmcgui.Dialog()

def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def notify(msg, title="Gemini Translator", duration=5000):
    """Native Shield notification for maximum visibility."""
    DIALOG.notification(title, msg, xbmcgui.NOTIFICATION_INFO, duration)

def get_model_string():
    """Maps the settings enum index to the official Google model strings."""
    model_index = ADDON.getSetting('model') or "0"
    mapping = {
        "0": "gemini-2.0-flash",
        "1": "gemini-1.5-flash",
        "2": "gemini-2.5-flash"
    }
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    if not api_key:
        log("ERROR: API Key is missing!")
        return None
        
    model_name = get_model_string()
    # BAZARR Logic: Flatten multi-line subs with [BR] and add Lxxx: prefix
    prefixed_lines = [f"L{i:03}: {text}" for i, text in enumerate(text_list)]
    input_text = "\n".join(prefixed_lines)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = (
        "### ROLE\nProfessional uncensored English-to-Romanian subtitle localizer.\n\n"
        "### RULES\n1. Translate line-by-line.\n"
        "2. Preserve 'Lxxx:' prefix exactly.\n"
        f"3. Return exactly {expected_count} lines.\n"
        "4. Style: Gritty, natural, adult Romanian.\n"
        "5. Return ONLY prefixes and translation."
    )

    attempts = 0
    while attempts < 3:
        try:
            temp_setting = float(ADDON.getSetting('temp') or 0.15)
            payload = {
                "contents": [{"parts": [{"text": f"{prompt}\n\n{input_text}"}]}],
                "generationConfig": {"temperature": temp_setting, "topP": 0.95}
            }
            r = requests.post(url, json=payload, timeout=30)
            r.raise_for_status()
            res_json = r.json()
            
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
            # Strip the Lxxx: prefixes and return clean list
            translated_lines = [re.sub(r'^L\d{3}:\s*', '', l.strip()) for l in raw_output if re.match(r'^L\d{3}:', l.strip())]
            
            if len(translated_lines) == expected_count:
                return translated_lines
            
            log(f"Mismatch ({model_name}): Expected {expected_count}, got {len(translated_lines)}")
            attempts += 1
            time.sleep(2)
        except Exception as e:
            attempts += 1
            log(f"API Error ({model_name}): {str(e)}")
            time.sleep(5)
    return None

def process_subtitles(original_path):
    log(f"Processing Subtitle: {original_path}")
    
    # Language Shield
    if any(tag in original_path.lower() for tag in ['.ro.', '.ron.', '.rum.', '_ro.']):
        log("Skipping: Path already indicates Romanian.")
        return
    
    # Custom Folder Logic
    save_dir = ADDON.getSetting('sub_folder')
    if not save_dir or not xbmcvfs.exists(save_dir):
        notify("Error: Custom save folder is not accessible!")
        return

    clean_name = os.path.basename(original_path).replace('.srt', '_RO.srt')
    save_path = os.path.join(save_dir, clean_name)

    # --- PRIORITY 1: CHECK FOR EXISTING RO VERSION ---
    if xbmcvfs.exists(save_path):
        log(f"Priority 1: Found existing RO sub at {save_path}. Skipping API.")
        xbmc.Player().setSubtitles(save_path)
        notify("Loading existing Romanian version...")
        return

    # --- PRIORITY 2: TRANSLATE ---
    notify("Gemini: Starting Translation...")
    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        
        # BAZARR Logic: Extraction
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        if not blocks:
            log("Error: Failed to parse SRT structure.")
            return
        
        timestamps = [(b[0], b[1]) for b in blocks]
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        
        all_translated = []
        idx = 0
        chunk_size = 50 

        while idx < len(texts):
            if not xbmc.Player().isPlaying(): return
            curr_size = min(chunk_size, len(texts) - idx)
            chunk = texts[idx:idx + curr_size]
            
            notify(f"Translating: {int((idx/len(texts))*100)}%", duration=1500)
            
            res = translate_text_only(chunk, len(chunk))
            if res:
                all_translated.extend(res)
                idx += len(chunk)
            else:
                notify("Gemini Error: Sync mismatch. Aborting.")
                return 

        # BAZARR Logic: Recomposition
        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]

        with xbmcvfs.File(save_path, 'w') as f:
            f.write("\n".join(final_srt))
            
        xbmc.Player().setSubtitles(save_path)
        notify("Success: Romanian Subtitles Active!")
        log(f"Final RO sub saved to: {save_path}")
        
    except Exception as e: 
        log(f"Critical Process Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def onPlayBackStopped(self):
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        
        custom_dir = ADDON.getSetting('sub_folder')
        if not custom_dir or not xbmcvfs.exists(custom_dir):
            return

        # STRICT: Monitor only the custom folder
        _, files = xbmcvfs.listdir(custom_dir)
        valid_files = [f for f in files if f.lower().endswith('.srt') and "_ro.srt" not in f.lower()]
        
        if valid_files:
            # Get full paths and sort by modification time (Newest first)
            full_paths = [os.path.join(custom_dir, f) for f in valid_files]
            full_paths.sort(key=lambda x: xbmcvfs.Stat(x).st_mtime(), reverse=True)
            newest_path = full_paths[0]
            
            if newest_path != self.last_processed:
                stat = xbmcvfs.Stat(newest_path)
                # GUARD: Size check (1KB) and Recency check (5 mins)
                if stat.st_size() > 1000 and (time.time() - stat.st_mtime() < 300):
                    log(f"New valid English sub detected: {newest_path}")
                    self.last_processed = newest_path
                    process_subtitles(newest_path)

if __name__ == '__main__':
    log("Gemini Service BOOT - Strict Custom Mode + RO Priority")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
