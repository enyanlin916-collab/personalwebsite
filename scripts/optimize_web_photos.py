#!/usr/bin/env python3
"""Create lightweight website-only JPEGs without modifying any source photos."""
from __future__ import annotations

import re
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
SRC_RE = re.compile(r'\bsrc=(["\'])([^"\']+)\1', re.IGNORECASE)

outcomes = {}


def optimized_path(source_name: str) -> str:
    source = ROOT / source_name
    category = "gallery" if source_name.startswith("photos/") else "home"
    target = ROOT / "web-images" / category / (source.stem.lower() + ".jpg")
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        image = ImageOps.exif_transpose(img)
        limit = 1600 if category == "gallery" else (900 if source_name == "me.jpg" else 1080)
        image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")
        save_kwargs = dict(format="JPEG", quality=83, optimize=True, progressive=True)
        profile = img.info.get("icc_profile")
        if profile:
            save_kwargs["icc_profile"] = profile
        image.save(target, **save_kwargs)
    original_bytes, new_bytes = source.stat().st_size, target.stat().st_size
    # Avoid introducing a larger image than the source.
    if new_bytes >= original_bytes * 0.92:
        target.unlink()
        outcomes[source_name] = (original_bytes, original_bytes, source_name)
        return source_name
    result = target.relative_to(ROOT).as_posix()
    outcomes[source_name] = (original_bytes, new_bytes, result)
    return result


def rewrite(page: str, eligible) -> int:
    path = ROOT / page
    html = path.read_text(encoding="utf-8")
    count = 0

    def replace_tag(match):
        nonlocal count
        tag = match.group(0)
        found = SRC_RE.search(tag)
        if not found:
            return tag
        original = found.group(2)
        if not eligible(original):
            return tag
        if original in outcomes:
            chosen = outcomes[original][2]
        else:
            chosen = optimized_path(original)
        if chosen != original:
            tag = tag.replace(found.group(0), f'src="{chosen}"', 1)
            count += 1
        # Hero images load immediately; off-screen gallery images are lazy-loaded.
        if page == "photography.html":
            hero = original.startswith("photos/hero")
            if "loading=" not in tag:
                tag = tag.replace("<img ", '<img loading="' + ("eager" if hero else "lazy") + '" ', 1)
            if "decoding=" not in tag:
                tag = tag.replace("<img ", '<img decoding="async" ', 1)
        return tag

    updated = IMG_RE.sub(replace_tag, html)
    if updated != html:
        path.write_text(updated, encoding="utf-8")
    return count


def main():
    first = rewrite("index.html", lambda p: p == "me.jpg" or bool(re.fullmatch(r"photo[1-6]\.[jJ][pP][gG]", p)))
    second = rewrite("photography.html", lambda p: p.startswith("photos/") and p.lower().endswith((".jpg", ".jpeg")))
    total_in = sum(x[0] for x in outcomes.values())
    total_out = sum(x[1] for x in outcomes.values())
    print("Updated references (homepage/gallery):", first, second)
    print(f"Original unique photo bytes: {total_in / 1_000_000:.2f} MB")
    print(f"Optimized referenced photo bytes: {total_out / 1_000_000:.2f} MB")
    print(f"Estimated reduction: {100 * (1 - total_out / total_in):.1f}%")
    for source, (old, new, result) in sorted(outcomes.items()):
        print(f"{source}: {old / 1_000_000:.2f} -> {new / 1_000_000:.2f} MB ({result})")


if __name__ == "__main__":
    main()
