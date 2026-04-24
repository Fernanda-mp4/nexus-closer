"""
Nexus Closer — Gerador de ícone cyberpunk + atalho de desktop.
Executa uma única vez: python scripts/gerar_icone.py
"""

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT  = Path(__file__).resolve().parent.parent
ICON  = ROOT / "assets" / "nexus_closer.ico"
NEON  = (0, 255, 65)
BLACK = (0, 0, 0)
DIM   = (13, 43, 18)
GLOW  = (0, 120, 30)


def _hexagon_points(cx, cy, r, rotation=0):
    pts = []
    for i in range(6):
        angle = math.radians(60 * i + rotation)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def _draw_frame(d: ImageDraw.ImageDraw, size: int) -> None:
    """Desenha a moldura hexagonal biomecânica."""
    cx = cy = size // 2
    outer = size * 0.46
    inner = size * 0.42

    # Glow em camadas (simula emissão neon)
    for offset, alpha in [(8, 20), (5, 50), (3, 90), (1, 160)]:
        pts_o = _hexagon_points(cx, cy, outer + offset, rotation=30)
        d.polygon(pts_o, outline=(0, 255, 65, alpha))

    # Hexágono externo
    pts_outer = _hexagon_points(cx, cy, outer, rotation=30)
    d.polygon(pts_outer, outline=NEON, width=max(1, size // 40))

    # Hexágono interno (moldura dupla)
    pts_inner = _hexagon_points(cx, cy, inner, rotation=30)
    d.polygon(pts_inner, outline=DIM, width=max(1, size // 64))


def _draw_letter(d: ImageDraw.ImageDraw, size: int) -> None:
    """Desenha 'N' geométrico com traços — sem dependência de fontes externas."""
    cx = cy = size // 2
    w  = size * 0.28   # largura do N
    h  = size * 0.32   # altura do N
    lw = max(2, size // 18)  # espessura dos traços

    x1, x2 = cx - w / 2, cx + w / 2
    y1, y2 = cy - h / 2, cy + h / 2

    # Glow por baixo
    for gw in [lw + 6, lw + 3, lw + 1]:
        d.line([(x1, y2), (x1, y1)],  fill=GLOW, width=gw)
        d.line([(x2, y1), (x2, y2)],  fill=GLOW, width=gw)
        d.line([(x1, y1), (x2, y2)],  fill=GLOW, width=gw)

    # Traços principais — "N"
    d.line([(x1, y2), (x1, y1)],  fill=NEON, width=lw)  # perna esquerda
    d.line([(x2, y1), (x2, y2)],  fill=NEON, width=lw)  # perna direita
    d.line([(x1, y1), (x2, y2)],  fill=NEON, width=lw)  # diagonal


def _draw_scanlines(d: ImageDraw.ImageDraw, size: int) -> None:
    step = max(3, size // 64)
    for y in range(0, size, step * 2):
        d.line([(0, y), (size, y)], fill=(0, 255, 65, 8), width=1)


def _draw_corners(d: ImageDraw.ImageDraw, size: int) -> None:
    """Glifos de circuito nos cantos."""
    m  = size * 0.08   # margem
    L  = size * 0.12   # comprimento do traço
    lw = max(1, size // 48)

    corners = [
        (m, m,     1,  1),
        (size-m, m,    -1,  1),
        (m, size-m,    1, -1),
        (size-m, size-m, -1, -1),
    ]
    for cx, cy, dx, dy in corners:
        d.line([(cx, cy), (cx + dx*L, cy)],       fill=DIM, width=lw)
        d.line([(cx, cy), (cx, cy + dy*L)],       fill=DIM, width=lw)
        # pequeno ponto terminal
        d.ellipse([(cx-lw, cy-lw), (cx+lw, cy+lw)], fill=NEON)


def _render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))   # fundo transparente
    d   = ImageDraw.Draw(img, "RGBA")

    _draw_scanlines(d, size)
    _draw_corners(d, size)
    _draw_frame(d, size)
    _draw_letter(d, size)
    return img


def gerar_ico() -> None:
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [_render(s) for s in sizes]

    # ICO salvo com a maior frame como base, as demais como tamanhos adicionais
    frames[0].save(
        str(ICON),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"Ícone salvo: {ICON}")


def criar_launcher() -> Path:
    bat = ROOT / "launch.bat"
    venv_python = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    python_exe  = str(venv_python) if venv_python.exists() else "pythonw"

    bat.write_text(
        f'@echo off\n'
        f'cd /d "{ROOT}"\n'
        f'start "" "{python_exe}" main.py\n',
        encoding="utf-8",
    )
    print(f"Launcher criado: {bat}")
    return bat


def criar_atalho_desktop(bat: Path) -> None:
    import subprocess
    desktop_raw = subprocess.check_output(
        ["powershell", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        text=True,
    ).strip()
    desktop = Path(desktop_raw)
    lnk     = desktop / "NEXUS CLOSER.lnk"

    # PS resolve o Desktop nativamente — evita encoding do "Área de Trabalho"
    ps_script = ROOT / "scripts" / "_temp_shortcut.ps1"
    ps_script.write_text(
        f'$desk = [Environment]::GetFolderPath("Desktop")\n'
        f'$lnk  = Join-Path $desk "NEXUS CLOSER.lnk"\n'
        f'$s = (New-Object -COM WScript.Shell).CreateShortcut($lnk)\n'
        f'$s.TargetPath = \'{bat}\'\n'
        f'$s.IconLocation = \'{ICON}\'\n'
        f'$s.WorkingDirectory = \'{ROOT}\'\n'
        f'$s.Description = \'NEXUS CLOSER // TERMINAL\'\n'
        f'$s.Save()\n'
        f'Write-Host "Atalho criado em: $lnk"\n',
        encoding="utf-8-sig",   # BOM garante que PS leia como UTF-8
    )
    result = os.system(f'powershell -ExecutionPolicy Bypass -File "{ps_script}"')
    ps_script.unlink(missing_ok=True)
    status = "OK" if result == 0 else f"ERRO cod={result}"
    print(f"Atalho desktop: {status}")


if __name__ == "__main__":
    gerar_ico()
    bat = criar_launcher()
    criar_atalho_desktop(bat)
    print("\nPronto! Clique duplo no atalho da área de trabalho para abrir o NEXUS CLOSER.")
