# -*- coding: utf-8 -*-
import re

def clean_sdh(text):
    """
    Removes SDH descriptions like [MUSIC PLAYING] or (SIGHING) 
    which often confuse translators.
    """
    # Remove text inside brackets [] or parentheses ()
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    # Remove speaker names like "JOHN: Hello" -> "Hello"
    text = re.sub(r'^[A-Z\s]+:\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def split_srt(content, max_lines=50):
    """
    Splits the SRT into chunks. 
    Gemini 2.0 Flash can handle 100+ lines easily.
    """
    lines = content.splitlines(True)
    chunks = []
    current_chunk = []
    line_count = 0

    for line in lines:
        current_chunk.append(line)
        # Split at blank lines to ensure we don't break a subtitle block
        if line.strip() == "":
            line_count += 1
            if line_count >= max_lines:
                chunks.append("".join(current_chunk))
                current_chunk = []
                line_count = 0
    
    if current_chunk:
        chunks.append("".join(current_chunk))
    return chunks

def merge_srt(chunks):
    """Joins translated chunks back together."""
    return "".join(chunks)

