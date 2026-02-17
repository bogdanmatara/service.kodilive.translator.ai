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
    # 1. LANGUAGE SHIELD: Stop if the file is already Romanian
    # We check for common Kodi language tags and our own suffix
    ignore_tags = ['_ro.', '.ro.', '.ron.', '.rum.', 'romanian', '_ro.srt']
    path_lower = original_path.lower()
    
    if any(tag in path_lower for tag in ignore_tags):
        log(f"Language Shield: {original_path} is already Romanian. Skipping.")
        return

    # 2. SANITIZE FILENAME: Remove virtual labels and Kodi junk
    base_name = os.path.basename(original_path)
    # Ignore virtual paths like 'eng' or 'default'
    if base_name.lower() in ['eng', 'eng.srt', 'default.srt', 'rum', 'rum.srt']:
        log("Skipping virtual/invalid path.")
        return

    # Strip out brackets like (External) or (Selected)
    clean_name = re.sub(r'\s*\(\w+\)', '', base_name)
    # Ensure our standard suffix
    clean_name = clean_name.replace('.srt', '_RO.srt')
    
    save_dir = "/storage/emulated/0/Download/sub/"
    if not xbmcvfs.exists(save_dir): xbmcvfs.mkdir(save_dir)
    save_path = os.path.join(save_dir, clean_name)

    # 3. CHECK IF ALREADY DONE (Wife-proof persistence)
    if xbmcvfs.exists(save_path):
        log(f"Loading existing translation: {save_path}")
        xbmc.Player().setSubtitles(save_path)
        return

    # 4. PROCEED ONLY IF VALID CONTENT EXISTS
    try:
        with xbmcvfs.File(original_path, 'r') as f: content = f.read()
        if not content or len(content) < 50: # Safety gate for 0-byte/junk files
            log("Source file empty or too small. Skipping.")
            return

        chunks = split_srt(content) 
        translated = []
        
        for i, c in enumerate(chunks):
            if not xbmc.Player().isPlaying(): return
            xbmc.executebuiltin(f'Notification(Gemini, Traducere: {int((i+1)/len(chunks)*100)}%, 1000)')
            res = translate_chunk(c)
            if res: translated.append(res)

        final_srt = clean_srt_content("\n".join(translated))
        
        # 5. FINAL WRITE GATE
        if len(final_srt) > 50:
            with xbmcvfs.File(save_path, 'w') as f: f.write(final_srt)
            xbmc.Player().setSubtitles(save_path)
            log(f"SUCCESS: Romanian subtitles active: {save_path}")
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


