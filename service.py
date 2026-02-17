# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, os, requests, json, re

ADDON = xbmcaddon.Addon()

def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def clean_sdh(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'^[A-Z\s]+:\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def split_srt(content, max_lines=100):
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
        "contents": [{"parts": [{"text": "Tradu acest SRT în Română (fără explicatii, păstrează timpul):\n\n" + text_block}]}],
        "generationConfig": {"temperature": 0.1}
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.json()['candidates'][0]['content']['parts'][0]['text']
    except: return None

def process_subtitles(original_path):
    # This is where the magic happens
    save_path = "/storage/emulated/0/Download/sub/" + os.path.basename(original_path).replace('.srt', '_RO.srt')
    if not xbmcvfs.exists("/storage/emulated/0/Download/sub/"): xbmcvfs.mkdir("/storage/emulated/0/Download/sub/")

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        chunks = split_srt(clean_sdh(content))
        translated = []
        for i, c in enumerate(chunks):
            # Discreet notification so she knows it's working
            xbmc.executebuiltin(f'Notification(Gemini, Traducere Automată: {int((i+1)/len(chunks)*100)}%, 1500)')
            res = translate_chunk(c)
            if res: translated.append(res)
        
        with xbmcvfs.File(save_path, 'w') as f: f.write("\n".join(translated))
        xbmc.Player().setSubtitles(save_path)
        log("Auto-translation complete and loaded.")
    except Exception as e: log(f"Fail: {e}")

class GeminiMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_processed = ""

    def check_for_subs(self):
        # 1. Try to get path from Kodi Player
        path = xbmc.Player().getSubtitles()
        
        # 2. If Kodi is hiding the path (common on Shield), scan the a4k temp folder directly
        if not path:
            temp_dir = "special://home/userdata/addon_data/service.subtitles.a4ksubtitles/temp/"
            if xbmcvfs.exists(temp_dir):
                dirs, files = xbmcvfs.listdir(temp_dir)
                for f in files:
                    if f.lower().endswith('.srt') and "_ro.srt" not in f.lower():
                        path = os.path.join(temp_dir, f)
                        break
        
        # 3. If we found a path and it's new, translate it
        if path and path != self.last_processed:
            if "_RO.srt" not in path:
                self.last_processed = path
                process_subtitles(path)
            else:
                self.last_processed = path

if __name__ == '__main__':
    log("Wife-Proof Gemini Service Started")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        if xbmc.Player().isPlaying():
            monitor.check_for_subs()
        if monitor.waitForAbort(10): break
