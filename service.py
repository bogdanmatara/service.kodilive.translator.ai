# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, os, requests, json, re, time

ADDON = xbmcaddon.Addon()
DIALOG = xbmcgui.Dialog()

def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def notify(msg, title="Gemini Translator", duration=5000):
    DIALOG.notification(title, msg, xbmcgui.NOTIFICATION_INFO, duration)

def get_model_string():
    model_index = ADDON.getSetting('model') or "0"
    mapping = {"0": "gemini-2.0-flash", "1": "gemini-1.5-flash", "2": "gemini-2.5-flash"}
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    
    # EXACT BAZARR PREFIXING
    prefixed_lines = [f"L{i:03}: {text}" for i, text in enumerate(text_list)]
    input_text = "\n".join(prefixed_lines)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    # EXACT BAZARR PROMPT
    prompt = (
        "### ROLE\nProfessional uncensored English-to-Romanian subtitle localizer.\n\n"
        "### RULES\n1. Translate line-by-line.\n2. Preserve 'Lxxx:' prefix.\n"
        f"3. Return exactly {expected_count} lines.\n4. Style: Gritty, natural, adult Romanian.\n"
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
            
            # EXACT BAZARR OUTPUT PARSING
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
            translated_lines = [re.sub(r'^L\d{3}:\s*', '', l.strip()) for l in raw_output if re.match(r'^L\d{3}:', l.strip())]
            
            if len(translated_lines) == expected_count:
                return translated_lines
            
            attempts += 1
            time.sleep(2)
        except Exception as e:
            attempts += 1
            log(f"API Error: {str(e)}")
            time.sleep(5)
    return None

def process_subtitles(original_path):
    save_dir = ADDON.getSetting('sub_folder')
    clean_name = os.path.basename(original_path).replace('.srt', '_RO.srt')
    save_path = os.path.join(save_dir, clean_name)

    if xbmcvfs.exists(save_path):
        log("RO sub found. Loading.")
        xbmc.Player().setSubtitles(save_path)
        return

    try:
        with xbmcvfs.File(original_path, 'r') as f: 
            content = f.read()

        # --- NORMALIZATION ---
        # Ensure we have Unix line endings so the Bazarr regex works perfectly
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # --- EXACT BAZARR REGEX ---
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        
        if not blocks:
            log("Bazarr Regex failed. Checking for encoding issues...")
            return

        # EXACT BAZARR BLOCK HANDLING
        timestamps = [(b[0], b[1]) for b in blocks]
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        
        all_translated = []
        idx = 0
        chunk_size = 50 

        while idx < len(texts):
            if not xbmc.Player().isPlaying(): return
            curr_size = min(chunk_size, len(texts) - idx)
            chunk = texts[idx:idx + curr_size]
            
            notify(f"Translating: {int((idx/len(texts))*100)}%")
            
            res = translate_text_only(chunk, len(chunk))
            if res:
                all_translated.extend(res)
                idx += len(chunk)
            else: return 

        # --- EXACT BAZARR RECOMPOSE ---
        final_srt = [f"{time_data[0]}\n{time_data[1]}\n{txt.replace(' [BR] ', '\n')}\n" for time_data, txt in zip(timestamps, all_translated)]

        with xbmcvfs.File(save_path, 'w') as f:
            f.write("\n".join(final_srt))
            
        xbmc.Player().setSubtitles(save_path)
        notify("Success: Romanian Subtitles Active!")
        
    except Exception as e: 
        log(f"Process Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        custom_dir = ADDON.getSetting('sub_folder')
        if not custom_dir or not xbmcvfs.exists(custom_dir): return

        _, files = xbmcvfs.listdir(custom_dir)
        valid_files = [f for f in files if f.lower().endswith('.srt') and "_ro.srt" not in f.lower()]
        
        if valid_files:
            full_paths = [os.path.join(custom_dir, f) for f in valid_files]
            full_paths.sort(key=lambda x: xbmcvfs.Stat(x).st_mtime(), reverse=True)
            newest_path = full_paths[0]
            
            if newest_path != self.last_processed:
                stat = xbmcvfs.Stat(newest_path)
                # Bazarr usually waits for the file to be fully written (sync)
                if stat.st_size() > 1000 and (time.time() - stat.st_mtime() < 300):
                    self.last_processed = newest_path
                    process_subtitles(newest_path)

if __name__ == '__main__':
    log("Gemini Service Starting - Pure Bazarr Logic")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
