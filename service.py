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
    """Saves to your verified custom path on Android."""
    # Using your verified path (case-sensitive for Android)
    custom_dir = "/storage/emulated/0/Download/sub"
    
    if not xbmcvfs.exists(custom_dir):
        xbmcvfs.mkdir(custom_dir)
    
    # Clean filename (removes .eng, .pl tags etc if present)
    base_name = os.path.basename(original_path)
    new_name = base_name.lower().replace('.eng.srt', '.srt').replace('.srt', '_RO.srt')
    
    target_path = os.path.join(custom_dir, new_name)
    log(f"Target save path: {target_path}")
    return target_path

def translate_with_progress(text_block):
    api_key = ADDON.getSetting('api_key')
    temp_val = float(ADDON.getSetting('temp') or 0.1)
    
    if not api_key:
        log("Error: API Key is missing in settings.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu următorul text SRT din Engleză în Română. "
        "Păstrează codurile de timp și numerotarea intacte. "
        "Folosește diacritice corecte (ș, ț, ă, î, â). Trimite DOAR textul tradus:\n\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {"temperature": temp_val, "topP": 0.95}
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
    log(f"Starting Translation: {original_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        clean_text = srt_utils.clean_sdh(content)
        chunks = srt_utils.split_srt(clean_text, max_lines=100)
        total = len(chunks)
        translated_chunks = []

        for i, chunk in enumerate(chunks):
            p = int(((i + 1) / total) * 100)
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere: {p}%, 2000)')
            
            res = translate_with_progress(chunk)
            if res:
                translated_chunks.append(res)
            else:
                return

        final_content = srt_utils.merge_srt(translated_chunks)
        with xbmcvfs.File(new_path, 'w') as f:
            f.write(final_content)

        log("Successfully saved translated file.")
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
            # Check the active subtitle path
            sub_path = self.getSubtitles()
            
            # If standard check fails, look for the a4k temp file specifically
            if not sub_path and self.isPlaying():
                # Some versions of Kodi on Android require a manual scan of the temp dir
                pass 

            if sub_path and sub_path != self.last_sub:
                if sub_path.lower().endswith('.srt') and "_RO.srt" not in sub_path:
                    log(f"Subtitle file found: {sub_path}")
                    self.last_sub = sub_path
                    process_subtitles(sub_path)
                else:
                    self.last_sub = sub_path
        except Exception as e:
            log(f"Monitoring error: {str(e)}")

if __name__ == '__main__':
    log("Gemini Translator Service started.")
    player = GeminiTranslatorPlayer()
    monitor = xbmc.Monitor()
    
    while not monitor.abortRequested():
        if xbmc.Player().isPlaying():
            player.trigger_check()
        if monitor.waitForAbort(5):
            break
