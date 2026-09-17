"""
Downloads a complete, public-domain King James Version Bible PDF into
data/kjv_bible.pdf.

Source: Internet Archive - "King James Bible Printable Format (PDF)"
Standardized 1769 KJV text, courtesy of the Crosswire Bible Society and
eBible.org. Public domain (outside the UK; see the Crown copyright note
at https://archive.org/details/kjvtextbible for the UK printing patent).

Run this on a machine with internet access:
    python download_bible.py
"""
import os
import sys

import requests

BIBLE_PDF_URL = "https://archive.org/download/kjvtextbible/KJVtext.pdf"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kjv_bible.pdf")


def download(url: str, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print(f"Downloading KJV Bible PDF from:\n  {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:5.1f}%  ({downloaded / 1e6:.1f} MB / {total / 1e6:.1f} MB)", end="")
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    try:
        download(BIBLE_PDF_URL, OUTPUT_PATH)
    except Exception as e:
        print(f"Download failed: {e}")
        print("You can also download it manually from:")
        print("  https://archive.org/details/kjvtextbible  (file: KJVtext.pdf)")
        print(f"and place it at: {OUTPUT_PATH}")
        sys.exit(1)