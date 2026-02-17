# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcvfs
import os
import requests
import json
import srt_utils 

ADDON = xbmcaddon.Addon()

def log(message):
    xbmc.log(f"[Gemini-RO-Translator] {message}", xbmc.LOGINFO)

def get_save_path(original_path):
    """Saves to your specific custom path or falls back to original folder."""
    # Hardcoded your verified path
    custom_path = "/storage/emulated/0/Download/sub"
    
    # Ensure the directory exists
    if not xbmcvfs.exists(custom_path):
        xbmcvfs.mkdir(custom_path)
    
    filename = os.path.basename(original_path).replace('.srt', '_RO.srt')
    
    if xbmcvfs.exists(custom_path):
        log(f"Saving to custom directory: {custom_path}")
        return os.path.join(custom_path, filename)
    
    return original_path.replace('.srt', '_RO.srt')

def translate_with_progress(text_block):
    api_key = ADDON.getSetting('api_key')
    temp_setting = float(ADDON.getSetting('temp') or 0.1)
    
    if not api_key:
        log("Error: API Key is missing.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu următorul text SRT din Engleză în Română. "
        "Reguli stricte: Păstrează codurile de timp și numerotarea. "
        "Folosește diacritice (ș, ț, ă, î, â). Trimite DOAR textul tradus:\n\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {"temperature": temp_setting, "topP": 0.95}
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"API Error: {str(e)}")
        return None

def process_subtitles(original_path):
    if not xbmcvfs.exists(original_path) or "_RO.srt" in original_path:
        return

    new_path = get_save_path(original_path)
    log(f"Processing: {original_path} -> {new_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        clean_content = srt_utils.clean_sdh(content)
        chunks = srt_utils.split_srt(clean_content, max_lines=100)
        total_chunks = len(chunks)
        translated_chunks = []

        for index, chunk in enumerate(chunks):
            progress = int(((index + 1) / total_chunks) * 100)
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere: {progress}%, 2000)')
            
            translated_part = translate_with_progress(chunk)
            if translated_part:
                translated_chunks.append(translated_part)
            else:
                return

        final_content = srt_utils.merge_srt(translated_chunks)
        with xbmcvfs.File(new_path, 'w') as f:
            f.write(final_content)

        xbmc.executebuiltin('Notification(Gemini RO, Traducere Finalizată!, 5000)')
        xbmc.sleep(1000)
        xbmc.Player().setSubtitles(new_path)

    except Exception as e:
        log(f"Process failed: {str(e)}")

class GeminiTranslatorPlayer(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.last_sub = ""

    def trigger_check(self):
        try:
            sub_path = self.getSubtitles()
            
            # Log what we see every 5 seconds if a movie is playing
            if sub_path:
                # log(f"Scanning sub path: {sub_path}") # Uncomment for heavy debugging
                if sub_path.endswith('.srt') and sub_path != self.last_sub:
                    if "_RO.srt" not in sub_path:
                        log(f"New target found: {sub_path}")
                        self.last_sub = sub_path
                        process_subtitles(sub_path)
                    else:
                        self.last_sub = sub_path
        except Exception as e:
            log(f"Trigger Error: {str(e)}")

if __name__ == '__main__':
    log("Service active.")
    player = GeminiTranslatorPlayer()
    monitor = xbmc.Monitor()
    
    while not monitor.abortRequested():
        if xbmc.Player().isPlaying():
            player.trigger_check()
        if monitor.waitForAbort(5):
            break
