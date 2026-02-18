# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, os, requests, json, re, time

ADDON = xbmcaddon.Addon()
def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def get_model_string():
    """Maps settings enum index to official Google model IDs."""
    model_index = ADDON.getSetting('model') or "0"
    mapping = {
        "0": "gemini-2.0-flash",
        "1": "gemini-1.5-flash",
        "2": "gemini-2.5-flash"
    }
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    
    # Bazarr Logic: Prefixing to maintain 1:1 line mapping
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
            res_json = r.json()
            
            # Extract lines and strip prefixes
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
            translated_lines = [re.sub(r'^L\d{3}:\s*', '', l.strip()) for l in raw_output if re.match(r'^L\d{3}:', l.strip())]
            
            if len(translated_lines) == expected_count:
                return translated_lines
            
            attempts += 1
            log(f"🔄 Count mismatch ({len(translated_lines)}/{expected_count}). Retry {attempts}...")
            time.sleep(2)
        except Exception as e:
            attempts += 1
            log(f"❌ API Error: {str(e)}")
            time.sleep(5)
    return None

def process_subtitles(original_path):
    # Rule A: Ignore if already Romanian
    if any(tag in original_path.lower() for tag in ['.ro.', '.ron.', '.rum.', '_ro.']): return
    
    # Rule B: Ignore virtual Kodi labels
    if os.path.basename(original_path).lower() in ['eng', 'eng.srt', 'rum', 'rum.srt']: return

    save_dir = ADDON.getSetting('sub_folder')
    if not save_dir or not xbmcvfs.exists(save_dir):
        log("Error: Custom sub_folder not set or not accessible.")
        return

    # Prepare output path
    clean_name = os.path.basename(original_path).replace('.srt', '_RO.srt')
    save_path = os.path.join(save_dir, clean_name)

    if xbmcvfs.exists(save_path):
        log(f"Loading existing translation: {save_path}")
        xbmc.Player().setSubtitles(save_path)
        return

    log(f"Starting Gemini translation for: {original_path}")
    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        
        # BAZARR Logic: Block Extraction
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        if not blocks: return
        
        timestamps = [(b[0], b[1]) for b in blocks]
        # BAZARR Logic: [BR] Flattening
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        
        all_translated = []
        idx = 0
        chunk_size = 50 

        while idx < len(texts):
            if not xbmc.Player().isPlaying(): return
            curr_size = min(chunk_size, len(texts) - idx)
            chunk = texts[idx:idx + curr_size]
            
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((idx/len(texts))*100)}%, 1000)')
            
            res = translate_text_only(chunk, len(chunk))
            if res:
                all_translated.extend(res)
                idx += len(chunk)
            else:
                log("Critical mismatch error. Aborting translation.")
                return 

        # BAZARR Logic: Recomposition
        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]

        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(final_srt))
            
        xbmc.Player().setSubtitles(save_path)
        log(f"✅ SUCCESS: Romanian sub active.")
        
    except Exception as e: log(f"Process Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def onPlayBackStopped(self):
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        
        # MONITOR ONLY THE CUSTOM FOLDER
        custom_dir = ADDON.getSetting('sub_folder')
        if not custom_dir or not xbmcvfs.exists(custom_dir): return

        _, files = xbmcvfs.listdir(custom_dir)
        
        # Find English .srt files that are NOT our Romanian version
        valid_files = [f for f in files if f.lower().endswith('.srt') and "_ro.srt" not in f.lower()]
        
        if valid_files:
            # Sort by modification time (Newest first)
            full_paths = [os.path.join(custom_dir, f) for f in valid_files]
            full_paths.sort(key=lambda x: xbmcvfs.Stat(x).st_mtime(), reverse=True)
            newest_path = full_paths[0]
            
            # Trigger only if it's a new file and has content
            if newest_path != self.last_processed:
                if xbmcvfs.Stat(newest_path).st_size() > 500:
                    self.last_processed = newest_path
                    process_subtitles(newest_path)

if __name__ == '__main__':
    log("Gemini Service BOOT - Strict Custom Folder Mode")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
