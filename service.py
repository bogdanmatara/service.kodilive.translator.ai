# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcvfs
import os
import requests
import json
import re

ADDON = xbmcaddon.Addon()

def log(message):
    xbmc.log(f"[Gemini-RO-Translator] {message}", xbmc.LOGINFO)

# --- Integrated SRT Utilities ---
def clean_sdh(text):
    """Removes SDH tags like [MUSIC] or (SIGHING) and speaker names."""
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'^[A-Z\s]+:\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def split_srt(content, max_lines=100):
    """Splits SRT into chunks at empty lines to prevent cutting sentences."""
    lines = content.splitlines(True)
    chunks = []
    current_chunk = []
    line_count = 0
    for line in lines:
        current_chunk.append(line)
        if line.strip() == "":
            line_count += 1
            if line_count >= max_lines:
                chunks.append("".join(current_chunk))
                current_chunk = []
                line_count = 0
    if current_chunk:
        chunks.append("".join(current_chunk))
    return chunks

# --- Core Translation Logic ---
def get_save_path(original_path):
    """Forces saving to the verified Android Download path."""
    custom_dir = "/storage/emulated/0/Download/sub"
    if not xbmcvfs.exists(custom_dir):
        xbmcvfs.mkdir(custom_dir)
    
    base_name = os.path.basename(original_path)
    # Ensure we create a clean filename for the Romanian version
    new_name = base_name.lower().replace('.eng.srt', '.srt').replace('.srt', '_RO.srt')
    return os.path.join(custom_dir, new_name)

def translate_chunk(text_block):
    """Calls Gemini 2.0 Flash API."""
    api_key = ADDON.getSetting('api_key')
    temp_val = float(ADDON.getSetting('temp') or 0.1)
    
    if not api_key:
        log("Error: API Key is missing in settings.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu acest text SRT din Engleză în Română. "
        "Păstrează codurile de timp și formatarea. Folosește diacritice (ș, ț, ă, î, â). "
        "Trimite DOAR textul tradus:\n\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {"temperature": temp_val, "topP": 0.95}
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"API Error: {str(e)}")
        return None

def process_subtitles(original_path):
    """Main orchestration: Read -> Clean -> Translate -> Save."""
    if "_RO.srt" in original_path:
        return
    
    new_path = get_save_path(original_path)
    log(f"STARTING TRANSLATION: {original_path} -> {new_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        clean_text = clean_sdh(content)
        chunks = split_srt(clean_text)
        total = len(chunks)
        translated_chunks = []

        for i, chunk in enumerate(chunks):
            progress = int(((i + 1) / total) * 100)
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere în curs: {progress}%, 2000)')
            
            res = translate_chunk(chunk)
            if res:
                translated_chunks.append(res)
            else:
                log("Chunk translation failed. Stopping.")
                return

        # Write final file
        with xbmcvfs.File(new_path, 'w') as f:
            f.write("\n".join(translated_chunks))

        log("Translation Successful. Loading new file.")
        xbmc.executebuiltin('Notification(Gemini RO, Traducere Finalizată!, 5000)')
        
        # Load the new subtitle into the player
        xbmc.sleep(1000)
        xbmc.Player().setSubtitles(new_path)
        
    except Exception as e:
        log(f"Process failed: {str(e)}")

# --- Player Monitoring ---
class GeminiPlayer(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.last_path = ""

    def trigger_check(self):
        try:
            # Check standard path
            path = self.getSubtitles()
            
            # Fallback for Kodi 21/22 virtual paths on Android
            if not path:
                path = xbmc.getInfoLabel('Player.SubtitlesPath')

            if path and path != self.last_path:
                if path.lower().endswith('.srt') and "_RO.srt" not in path:
                    log(f"NEW SUBTITLE DETECTED: {path}")
                    self.last_path = path
                    process_subtitles(path)
                else:
                    # Ignore non-srt or already translated files
                    self.last_path = path 
        except Exception as e:
            log(f"Monitoring error: {str(e)}")

# --- Service Loop ---
if __name__ == '__main__':
    log("Gemini Translator Service BOOT")
    try:
        player = GeminiPlayer()
        monitor = xbmc.Monitor()
        
        while not monitor.abortRequested():
            if xbmc.Player().isPlaying():
                player.trigger_check()
            
            # Check every 5 seconds
            if monitor.waitForAbort(5):
                break
    except Exception as e:
        log(f"CRITICAL STARTUP ERROR: {str(e)}")
