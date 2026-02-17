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

# --- Integrated srt_utils functions ---
def clean_sdh(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'^[A-Z\s]+:\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def split_srt(content, max_lines=50):
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

# --- Main Logic ---
def get_save_path(original_path):
    custom_dir = "/storage/emulated/0/Download/sub"
    if not xbmcvfs.exists(custom_dir):
        xbmcvfs.mkdir(custom_dir)
    
    base_name = os.path.basename(original_path)
    new_name = base_name.lower().replace('.eng.srt', '.srt').replace('.srt', '_RO.srt')
    return os.path.join(custom_dir, new_name)

def translate_chunk(text_block):
    api_key = ADDON.getSetting('api_key')
    temp_val = float(ADDON.getSetting('temp') or 0.1)
    
    if not api_key:
        log("Error: API Key is empty.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = "Tradu acest SRT din Engleză în Română. Păstrează timpul și formatul. Folosește diacritice. Trimite doar textul:\n\n"

    payload = {
        "contents": [{"parts": [{"text": prompt + text_block}]}],
        "generationConfig": {"temperature": temp_val}
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"API Error: {str(e)}")
        return None

def process_subtitles(original_path):
    if "_RO.srt" in original_path: return
    
    new_path = get_save_path(original_path)
    log(f"Starting: {original_path} -> {new_path}")

    try:
        with xbmcvfs.File(original_path, 'r') as f:
            content = f.read()

        clean_text = clean_sdh(content)
        chunks = split_srt(clean_text)
        total = len(chunks)
        translated_chunks = []

        for i, chunk in enumerate(chunks):
            progress = int(((i + 1) / total) * 100)
            xbmc.executebuiltin(f'Notification(Gemini RO, Traducere: {progress}%, 2000)')
            res = translate_chunk(chunk)
            if res: translated_chunks.append(res)
            else: return

        with xbmcvfs.File(new_path, 'w') as f:
            f.write("\n".join(translated_chunks))

        xbmc.executebuiltin('Notification(Gemini RO, Gata!, 5000)')
        xbmc.Player().setSubtitles(new_path)
    except Exception as e:
        log(f"Fail: {str(e)}")

class GeminiPlayer(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.last_path = ""

    def trigger(self):
        path = self.getSubtitles()
        if path and path != self.last_path and path.endswith('.srt') and "_RO.srt" not in path:
            self.last_path = path
            process_subtitles(path)

if __name__ == '__main__':
    log("Gemini Translator Service BOOT")
    try:
        player = GeminiPlayer()
        monitor = xbmc.Monitor()
        while not monitor.abortRequested():
            if xbmc.Player().isPlaying():
                player.trigger()
            if monitor.waitForAbort(5):
                break
    except Exception as e:
        log(f"CRITICAL STARTUP ERROR: {str(e)}")
