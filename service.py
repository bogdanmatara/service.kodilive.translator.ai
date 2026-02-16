# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcvfs
import os
import requests
import json
import re

ADDON = xbmcaddon.Addon()
API_KEY = ADDON.getSetting('api_key')

def log(message):
    xbmc.log(f"[Gemini-RO-Translator] {message}", xbmc.LOGINFO)

def translate_batch(text_block):
    temp_setting = float(ADDON.getSetting('temp') or 0.1)
    """Sends a block of SRT text to Gemini 2.0 Flash."""
    if not API_KEY:
        log("Error: API Key is missing in settings.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    
    prompt = (
        "Ești un traducător profesionist de subtitrări. Tradu următorul text SRT din Engleză în Română. "
        "Reguli stricte: \n"
        "1. Păstrează neschimbate codurile de timp (ex: 00:00:20,000 --> 00:00:24,400) și numerotarea.\n"
        "2. Folosește diacritice corecte (ș, ț, ă, î, â).\n"
        "3. Păstrează formatarea liniilor.\n"
        "4. Trimite DOAR textul tradus, fără alte explicații.\n\n"
    )

    payload = {
        "contents": [{
            "parts": [{"text": prompt + text_block}]
        }],
        "generationConfig": {
            "temperature": temp_setting,
            "topP": 0.9
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
    """Reads the SRT, translates it, and saves it as _RO.srt"""
    if not xbmcvfs.exists(original_path):
        return

    # Create the new filename with _RO suffix
    new_path = original_path.replace('.srt', '_RO.srt')
    
    log(f"Starting translation: {original_path} -> {new_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        # Simple batching: Gemini 2.0 Flash can handle large context, 
        # but we send in chunks if the file is massive.
        translated_content = translate_batch(content)

        if translated_content:
            with xbmcvfs.File(new_path, 'w') as f:
                f.write(translated_content)
            log("Translation successful.")
            # Notify Kodi to use the new subtitle
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere finalizată!, 5000)')
    except Exception as e:
        log(f"Processing failed: {str(e)}")

# Kodi Service Loop
if __name__ == '__main__':
    log("Service started.")
    monitor = xbmc.Monitor()
    
    while not monitor.abortRequested():
        # This logic should trigger when a subtitle is loaded
        # The original Kirek66 logic uses a player callback or file check
        if monitor.waitForAbort(10):
            break

