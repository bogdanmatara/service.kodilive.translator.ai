# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, os, requests, json, re

ADDON = xbmcaddon.Addon()
def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def clean_srt_content(text):
    text = re.sub(r'```[a-z]*', '', text).replace('```', '')
    match = re.search(r'(\d+\s+\d{2}:\d{2}:\d{2})', text)
    if match: text = text[text.find(match.group(1)):]
    if not text.strip().startswith('1'): text = "1\n" + text
    return text.strip()

def clean_sdh(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'^[A-Z\s]+:\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def split_srt(content, max_lines=50):
    lines = content.splitlines(True)
    chunks, current_chunk, count = [], [], 0
    for line in lines:
        current_chunk.append(line)
        if line.strip() == "":
            count += 1
            if count >= max_lines:
                chunks.append("".join(current_chunk))
                current_chunk, count = [], 0
    if current_chunk: chunks.append("".join(current_chunk))
    return chunks

def translate_chunk(text_block):
    api_key = ADDON.getSetting('api_key')
    if not api_key: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Tradu acest SRT în Română. Păstrează timpul. Trimite DOAR codul SRT:\n\n" + text_block}]}],
        "generationConfig": {"temperature": 0.1}
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.json()['candidates'][0]['content']['parts'][0]['text']
    except: return None

def process_subtitles(original_path):
    save_dir = "/storage/emulated/0/Download/sub/"
    if not xbmcvfs.exists(save_dir): xbmcvfs.mkdir(save_dir)
    
    filename = os.path.basename(original_path).replace('.srt', '_RO.srt')
    save_path = os.path.join(save_dir, filename)

    # WIFE-PROOF: If we already translated THIS specific file, just load it!
    if xbmcvfs.exists(save_path):
        log(f"Already have translation: {save_path}. Loading...")
        xbmc.Player().setSubtitles(save_path)
        return

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        chunks = split_srt(clean_sdh(content))
        translated = []
        
        for i, c in enumerate(chunks):
            # Abort if movie stopped
            if not xbmc.Player().isPlaying(): 
                log("Playback stopped. Aborting translation.")
                return
                
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((i+1)/len(chunks)*100)}%, 1000)')
            res = translate_chunk(c)
            if res: translated.append(res)
        
        final_srt = clean_srt_content("\n".join(translated))
        with xbmcvfs.File(save_path, 'w') as f: f.write(final_srt)
        
        xbmc.Player().setSubtitles(save_path)
        log("SUCCESS: Auto-translation loaded.")
    except Exception as e: log(f"Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def onPlayBackStopped(self):
        self.last_processed = "" # Reset memory so next movie triggers fresh
        log("Playback stopped - memory cleared.")

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
            else:
                self.last_processed = path

if __name__ == '__main__':
    log("Wife-Proof Service Started v2")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break

