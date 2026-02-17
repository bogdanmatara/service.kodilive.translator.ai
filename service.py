# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, os, requests, json, re, time

ADDON = xbmcaddon.Addon()
def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def get_model_string():
    model_index = ADDON.getSetting('model') or "0"
    mapping = {"0": "gemini-2.0-flash", "1": "gemini-1.5-flash", "2": "gemini-2.5-flash"}
    return mapping.get(model_index, "gemini-2.0-flash")

def translate_text_only(text_list, expected_count):
    api_key = ADDON.getSetting('api_key')
    model_name = get_model_string()
    prefixed_lines = [f"L{i:03}: {text}" for i, text in enumerate(text_list)]
    input_text = "\n".join(prefixed_lines)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
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
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
            
            translated_lines = [re.sub(r'^L\d{3}:\s*', '', l.strip()) for l in raw_output if re.match(r'^L\d{3}:', l.strip())]
            
            if len(translated_lines) == expected_count:
                return translated_lines
            attempts += 1
            log(f"🔄 Retry {attempts} for {model_name}...")
            time.sleep(2)
        except Exception as e:
            attempts += 1
            log(f"❌ API Error: {str(e)}")
            time.sleep(5)
    return None

def process_subtitles(original_path):
    # Rule A: Skip if already Romanian or virtual label
    if any(tag in original_path.lower() for tag in ['.ro.', '.ron.', '.rum.', '_ro.']): return
    if os.path.basename(original_path).lower() in ['eng', 'eng.srt']: return

    # Save locally on Shield
    save_dir = "/storage/emulated/0/Download/sub/"
    if not xbmcvfs.exists(save_dir): xbmcvfs.mkdir(save_dir)
    save_path = os.path.join(save_dir, os.path.basename(original_path).replace('.srt', '_RO.srt'))

    if xbmcvfs.exists(save_path):
        xbmc.Player().setSubtitles(save_path)
        return

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        
        # BAZARR EXTRACTION
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
            chunk = texts[idx:idx + curr_size]
            
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((idx/len(texts))*100)}%, 1000)')
            
            res = translate_text_only(chunk, len(chunk))
            if res:
                all_translated.extend(res)
                idx += len(chunk)
            else: return 

        # BAZARR RECOMPOSE
        final_srt = [f"{t[0]}\n{t[1]}\n{txt.replace(' [BR] ', '\n')}\n" for t, txt in zip(timestamps, all_translated)]

        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(final_srt))
            
        xbmc.Player().setSubtitles(save_path)
        log(f"✅ PROTECTED LOCAL SAVE: {save_path}")
        
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
        
        # BAZARR LOGIC: If path is empty (common with WebDAV), scan local temp
        if not path or "dav://" in path:
            temp_dir = "special://home/userdata/addon_data/service.subtitles.a4ksubtitles/temp/"
            if xbmcvfs.exists(temp_dir):
                _, files = xbmcvfs.listdir(temp_dir)
                for f in sorted(files, reverse=True):
                    if f.lower().endswith('.srt') and "_ro.srt" not in f.lower():
                        path = os.path.join(temp_dir, f)
                        break
        
        if path and path != self.last_processed:
            self.last_processed = path
            process_subtitles(path)

if __name__ == '__main__':
    log("Gemini Service BOOT - Protected DAV Mode")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
