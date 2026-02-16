# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcvfs
import os
import requests
import json

ADDON = xbmcaddon.Addon()
API_KEY = ADDON.getSetting('api_key')

def log(message):
    xbmc.log(f"[Gemini-RO-Translator] {message}", xbmc.LOGINFO)

def get_save_path(original_path):
    """Determines the path to save the _RO.srt file based on Kodi settings."""
    # Check Kodi's 'Custom Subtitle Folder' setting
    custom_path = xbmc.getCleanLibCollation(xbmc.getRegion('subtitles.custompath')) or ""
    
    filename = os.path.basename(original_path).replace('.srt', '_RO.srt')
    
    if custom_path and xbmcvfs.exists(custom_path):
        log(f"Using Custom Subtitle Path: {custom_path}")
        return os.path.join(custom_path, filename)
    
    # Default: Save next to the original subtitle/video
    return original_path.replace('.srt', '_RO.srt')

def translate_batch(text_block):
    temp_setting = float(ADDON.getSetting('temp') or 0.1)
    if not API_KEY:
        log("Error: API Key is missing.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu următorul text SRT din Engleză în Română. "
        "Reguli stricte: Păstrează codurile de timp, numerotarea și formatarea. "
        "Folosește diacritice (ș, ț, ă, î, â). Trimite DOAR textul tradus:\n\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {"temperature": temp_setting, "topP": 0.9}
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"API Error: {str(e)}")
        return None

def process_subtitles(original_path):
    if not xbmcvfs.exists(original_path):
        return

    new_path = get_save_path(original_path)
    log(f"Translating: {original_path} -> {new_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        translated_content = translate_batch(content)

        if translated_content:
            with xbmcvfs.File(new_path, 'w') as f:
                f.write(translated_content)
            log("Translation successful.")
            xbmc.Player().setSubtitles(new_path) # Load it immediately
            xbmc.executebuiltin('Notification(Gemini RO, Traducere finalizată!, 5000)')
    except Exception as e:
        log(f"Processing failed: {str(e)}")

if __name__ == '__main__':
    log("Service started.")
    monitor = xbmc.Monitor()
    # Note: You still need a trigger (like a Player class) to call process_subtitles()
    while not monitor.abortRequested():
        if monitor.waitForAbort(10):
            break
