# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcvfs
import os
import requests
import json
import srt_utils  # Ensure srt_utils.py is in the same folder

ADDON = xbmcaddon.Addon()

def log(message):
    xbmc.log(f"[Gemini-RO-Translator] {message}", xbmc.LOGINFO)

def get_save_path(original_path):
    """Determines where to save the _RO.srt file based on Kodi settings."""
    custom_path = xbmc.getCleanLibCollation(xbmc.getRegion('subtitles.custompath')) or ""
    filename = os.path.basename(original_path).replace('.srt', '_RO.srt')
    
    if custom_path and xbmcvfs.exists(custom_path):
        log(f"Using Custom Subtitle Path: {custom_path}")
        return os.path.join(custom_path, filename)
    
    return original_path.replace('.srt', '_RO.srt')

def translate_with_progress(text_block):
    """Sends a specific chunk of text to Gemini 2.0 Flash."""
    api_key = ADDON.getSetting('api_key')
    temp_setting = float(ADDON.getSetting('temp') or 0.1)
    
    if not api_key:
        log("Error: API Key is missing in settings.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu următorul text SRT din Engleză în Română. "
        "Reguli stricte: \n"
        "1. Păstrează neschimbate codurile de timp și numerotarea.\n"
        "2. Folosește diacritice corecte (ș, ț, ă, î, â).\n"
        "3. Păstrează formatarea originală.\n"
        "4. Trimite DOAR textul tradus, fără alte mesaje.\n\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {
            "temperature": temp_setting,
            "topP": 0.95
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"API Error: {str(e)}")
        return None

def process_subtitles(original_path):
    """The main orchestration logic: Read -> Clean -> Split -> Translate -> Merge -> Save."""
    if not xbmcvfs.exists(original_path) or "_RO.srt" in original_path:
        return

    new_path = get_save_path(original_path)
    log(f"Starting process for: {original_path}")

    try:
        # 1. Read original file
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        # 2. Clean SDH using srt_utils
        clean_content = srt_utils.clean_sdh(content)
        
        # 3. Split into chunks for API limits and progress tracking
        chunks = srt_utils.split_srt(clean_content, max_lines=100)
        total_chunks = len(chunks)
        translated_chunks = []

        log(f"Split into {total_chunks} chunks.")

        # 4. Loop through chunks and translate
        for index, chunk in enumerate(chunks):
            # Calculate and show progress
            progress = int(((index + 1) / total_chunks) * 100)
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere în curs: {progress}%, 2000)')
            
            translated_part = translate_with_progress(chunk)
            if translated_part:
                translated_chunks.append(translated_part)
            else:
                log("Chunk translation failed. Aborting.")
                return

        # 5. Merge chunks back together
        final_content = srt_utils.merge_srt(translated_chunks)

        # 6. Save the new Romanian file
        with xbmcvfs.File(new_path, 'w') as f:
            f.write(final_content)

        log("Success! File saved.")
        xbmc.executebuiltin('Notification(Gemini RO, Traducere 100% - Finalizată!, 5000)')
        
        # 7. Automatically switch to the new subtitles
        xbmc.sleep(1000)
        xbmc.Player().setSubtitles(new_path)

    except Exception as e:
        log(f"Processing error: {str(e)}")

class GeminiTranslatorPlayer(xbmc.Player):
    """The 'Sensor' that watches for subtitle events."""
    def onPlayBackStarted(self):
        log("Playback started. Waiting for subtitle track...")
        xbmc.sleep(3000) 
        self.trigger_check()

    def onSubtitleData(self, data):
        # Triggers if the user manually changes subtitles during playback
        self.trigger_check()

    def trigger_check(self):
        sub_path = self.getSubtitles()
        # Only start if it's an English/Original SRT and not already our RO version
        if sub_path and sub_path.endswith('.srt') and "_RO.srt" not in sub_path:
            process_subtitles(sub_path)

# --- Main Service Loop ---
if __name__ == '__main__':
    log("Service initialized and waiting for playback.")
    player = GeminiTranslatorPlayer()
    monitor = xbmc.Monitor()
    
    while not monitor.abortRequested():
        # Keeps the service alive
        if monitor.waitForAbort(1):
            break
