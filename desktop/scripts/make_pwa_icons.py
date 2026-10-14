"""Erzeugt die App-Icons der PWA im gleichen Stil wie das Tray-Symbol am PC.

Aufruf (aus pwa/):  npm run icons
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[2] / "pwa" / "public" / "icons"
BG = (17, 17, 20, 255)
WHITE = (242, 242, 242, 255)


def draw_mic(size: int, padding: float) -> Image.Image:
    """Mikrofon auf dunklem Grund. `padding` = Anteil Rand (maskable Icons brauchen
    viel Rand, weil Android sie z. B. rund oder als Tropfen ausschneidet)."""
    img = Image.new("RGBA", (size, size), BG)
    d = ImageDraw.Draw(img)
    s = size * (1 - 2 * padding) / 64  # Zeichnung ist für 64 px entworfen
    o = size * padding

    def p(x, y):
        return (o + x * s, o + y * s)

    w = max(2, round(3 * s))
    d.rounded_rectangle((*p(24, 12), *p(40, 38)), radius=8 * s, fill=WHITE)
    d.arc((*p(17, 22), *p(47, 46)), start=0, end=180, fill=WHITE, width=w)
    d.line((*p(32, 46), *p(32, 52)), fill=WHITE, width=w)
    d.line((*p(24, 52), *p(40, 52)), fill=WHITE, width=w)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_mic(192, 0.12).save(OUT / "icon-192.png")
    draw_mic(512, 0.12).save(OUT / "icon-512.png")
    draw_mic(512, 0.22).save(OUT / "maskable-512.png")
    draw_mic(180, 0.14).save(OUT / "apple-touch-icon.png")
    print("Icons gespeichert in", OUT)


if __name__ == "__main__":
    main()
