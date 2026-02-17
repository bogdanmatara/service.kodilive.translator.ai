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
    
    # Bazarr Logic: Flattening and Prefixing
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
            
            # Robust Parsing: Handles cases with leading/trailing spaces around Lxxx:
            translated_lines = []
            for line in raw_output:
                clean_l = line.strip()
                if re.match(r'^L\d{3}:', clean_l):
                    # Strip prefix and any immediate space after it
                    translated_lines.append(re.sub(r'^L\d{3}:\s*', '', clean_l))
            
            if len(translated_lines) == expected_count:
                return translated_lines
            
            attempts += 1
            log(f"🔄 Model {model_name} Count Mismatch ({len(translated_lines)}/{expected_count}). Retry {attempts}...")
            time.sleep(2)
        except Exception as e:
            attempts += 1
            log(f"❌ API Error ({model_name}): {str(e)}")
            time.sleep(5)
    return None

def process_subtitles(original_path):
    # Language Shield
    if any(tag in original_path.lower() for tag in ['.ro.', '.ron.', '.rum.', '_ro.']):
        return

    save_dir = "/storage/emulated/0/Download/sub/"
    if not xbmcvfs.exists(save_dir): xbmcvfs.mkdir(save_dir)
    save_path = os.path.join(save_dir, os.path.basename(original_path).replace('.srt', '_RO.srt'))

    if xbmcvfs.exists(save_path):
        xbmc.Player().setSubtitles(save_path)
        return

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        
        # Bazarr Extraction Logic
        blocks = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n$|$)', content, re.DOTALL)
        if not blocks: return
        
        timestamps = [(b[0], b[1]) for b in blocks]
        # Bazarr [BR] Flattening
        texts = [b[2].replace('\n', ' [BR] ') for b in blocks]
        
        all_translated = []
        idx = 0
        chunk_size = 50 

        while idx < len(texts):
            if not xbmc.Player().isPlaying(): return
            current_chunk_size = min(chunk_size, len(texts) - idx)
            chunk = texts[idx:idx + current_chunk_size]
            
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((idx/len(texts))*100)}%, 1000)')
            
            res = translate_text_only(chunk, len(chunk))
            if res:
                all_translated.extend(res)
                idx += len(chunk)
            else:
                log("Handshake failed. Script Aborted to protect sync.")
                return 

        # Bazarr Recomposition Logic
        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]

        with xbmcvfs.File(save_path, 'w') as f:
            f.write("\n".join(final_srt))
            
        xbmc.Player().setSubtitles(save_path)
        log(f"✅ PROTECTED SAVE: {save_path}")
        
    except Exception as e: log(f"Process Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def onPlayBackStopped(self):
        self.last_processed = ""

    def check_for_subs(self):
        if not xbmc.Player().isPlaying(): return
        path = xbmc.Player().getSubtitles()
        if not path:
            temp_dir = "special://home/userdata/addon_data/service.subtitles.a4ksubtitles/temp/"
            if xbmcvfs.exists(temp_dir):
                _, files = xbmcvfs.listdir(temp_dir)
                for f in files:
                    if f.lower().endswith('.srt') and "_ro.srt" not in f.lower():
                        path = os.path.join(temp_dir, f)
                        break
        
        if path and path != self.last_processed:
            if "_RO.srt" not in path:
                self.last_processed = path
                process_subtitles(path)
            else: self.last_processed = path

if __name__ == '__main__':
    log("Gemini Service BOOT - v2.5 Flash Ready")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
