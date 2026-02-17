# -*- coding: utf-8 -*-
import xbmc, xbmcaddon, xbmcvfs, os, requests, json, re

ADDON = xbmcaddon.Addon()
def log(msg): xbmc.log(f"[Gemini-RO-Translator] {msg}", xbmc.LOGINFO)

def clean_srt_content(text):
    """Ensures the SRT is strictly formatted for Kodi."""
    text = re.sub(r'```[a-z]*', '', text).replace('```', '')
    # Find first index or timestamp
    match = re.search(r'(\d+\s+\d{2}:\d{2}:\d{2})', text)
    if match: text = text[text.find(match.group(1)):]
    return text.strip()

def split_srt(content, max_lines=50): # Reduced chunk size for better stability
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
    
    # Strictly instructing the AI NOT to skip any indexes
    prompt = (
        "Tradu acest text SRT în Română. \n"
        "REGULI STRICTE:\n"
        "1. Păstrează TOATE numerele de index (ex: 160, 161).\n"
        "2. Păstrează TOATE codurile de timp.\n"
        "3. NU lăsa linii goale dacă în engleză există text (chiar și sunete).\n"
        "4. Trimite DOAR codul SRT final.\n\n"
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
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

    if xbmcvfs.exists(save_path):
        xbmc.Player().setSubtitles(save_path)
        return

    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        
        # WE REMOVED clean_sdh(content) HERE
        chunks = split_srt(content) 
        translated = []
        
        for i, c in enumerate(chunks):
            if not xbmc.Player().isPlaying(): return
                
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((i+1)/len(chunks)*100)}%, 1000)')
            res = translate_chunk(c)
            if res: 
                translated.append(res)
            else:
                log(f"Warning: Chunk {i} failed.")

        final_srt = clean_srt_content("\n".join(translated))
        with xbmcvfs.File(save_path, 'w') as f: f.write(final_srt)
        
        xbmc.Player().setSubtitles(save_path)
        log("Success: Auto-translation loaded with all lines preserved.")
    except Exception as e: log(f"Fail: {e}")

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
    log("Wife-Proof Service Started - Gaps Fix")
    monitor = GeminiMonitor()
    while not monitor.abortRequested():
        monitor.check_for_subs()
        if monitor.waitForAbort(10): break
