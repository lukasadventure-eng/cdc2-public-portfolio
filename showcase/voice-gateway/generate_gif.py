#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Gera GIF demonstrativo da interface do Voice Gateway."""

import asyncio
import subprocess
import time
import os
import sys
from pathlib import Path

# Adicionar o diretório do projeto ao path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

def log(msg):
    print(msg, flush=True)

async def generate_gif():
    """Inicia o servidor, captura GIF da interface, para o servidor."""
    
    # Mudar para o diretório do showcase
    os.chdir(project_dir)
    
    # Configurar ambiente
    env = os.environ.copy()
    env['VOICE_GATEWAY_TOKEN'] = 'demo-token-para-gif'
    env['VOICE_GATEWAY_EXIGIR_TOKEN'] = 'false'
    env['VOICE_GATEWAY_STT_PROVEDOR'] = 'browser'
    env['VOICE_GATEWAY_TTS_PROVEDOR'] = 'browser'
    
    log("[INFO] Iniciando Voice Gateway...")
    
    # Iniciar servidor em background na porta 8766 (porta 8765 é do Painel Vigia)
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "voice_gateway.run", "--host", "127.0.0.1", "--port", "8766"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Aguardar servidor iniciar
    log("[INFO] Aguardando servidor iniciar...")
    await asyncio.sleep(3)
    
    # Verificar se servidor está rodando
    import httpx
    async with httpx.AsyncClient() as client:
        for i in range(10):
            try:
                resp = await client.get("http://127.0.0.1:8766/health", timeout=2.0)
                if resp.status_code == 200:
                    log("[OK] Servidor pronto!")
                    break
            except:
                pass
            await asyncio.sleep(1)
        else:
            log("[ERRO] Servidor não iniciou a tempo")
            server_proc.terminate()
            return False
    
    # Importar playwright aqui para evitar problemas de importação
    from playwright.async_api import async_playwright
    
    log("[INFO] Iniciando captura com Playwright...")
    
    async with async_playwright() as p:
        # Usar chromium headless
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1.0,
        )
        
        page = await context.new_page()
        
        # Navegar para a interface
        await page.goto("http://127.0.0.1:8766/", wait_until="networkidle")
        await asyncio.sleep(1)
        
        # Capturar frames para GIF
        frames = []
        duration = 8000  # 8 segundos
        fps = 10
        frame_count = int(duration / 1000 * fps)
        
        log(f"[INFO] Capturando {frame_count} frames...")
        
        async def safe_click(selector, timeout=3000):
            try:
                await page.click(selector, timeout=timeout)
            except Exception as e:
                log(f"  [aviso] clique falhou em {selector}: {e}")

        for i in range(frame_count):
            # Interações durante a captura
            if i == 3:
                # Digitar mensagem
                await page.type("#text", "Olá, como você está?")
            elif i == 10:
                # Enviar mensagem
                await page.click("#send")
            elif i == 15:
                # Limpar campo de texto
                await page.evaluate("document.getElementById('text').value = ''")
            elif i == 25:
                # Abrir configurações
                await safe_click("#settingsBtn")
            elif i == 35:
                # Fechar configurações
                await page.evaluate("document.getElementById('drawer').hidden = true")
            elif i == 45:
                # Abrir painel de operações
                await safe_click("#opsBtn")
            elif i == 55:
                # Fechar painel de operações
                await page.evaluate("document.getElementById('opsPanel').hidden = true")
            
            # Capturar frame
            screenshot = await page.screenshot(type="png")
            frames.append(screenshot)
            
            # Progresso
            if i % 10 == 0:
                log(f"  Frame {i+1}/{frame_count}")
            
            await asyncio.sleep(1/fps)
        
        await browser.close()
    
    log("[INFO] Parando servidor...")
    server_proc.terminate()
    server_proc.wait(timeout=5)
    
    log("[INFO] Gerando GIF...")
    
    # Salvar frames temporários e gerar GIF com PIL
    from PIL import Image
    import io
    
    pil_frames = []
    for frame_bytes in frames:
        img = Image.open(io.BytesIO(frame_bytes))
        # Redimensionar para GIF mais leve
        img = img.resize((640, 360), Image.Resampling.LANCZOS)
        pil_frames.append(img)
    
    # Salvar GIF
    gif_path = project_dir / "demo.gif"
    pil_frames[0].save(
        gif_path,
        save_all=True,
        append_images=pil_frames[1:],
        duration=1000//fps,
        loop=0,
        optimize=True,
    )
    
    # Verificar tamanho
    size_mb = gif_path.stat().st_size / (1024 * 1024)
    log(f"[OK] GIF gerado: {gif_path} ({size_mb:.1f} MB)")
    
    # Se muito grande, otimizar mais
    if size_mb > 5:
        log("[AVISO] GIF grande, otimizando...")
        # Reduzir frames
        optimized = pil_frames[::2]  # Pegar cada 2 frames
        pil_frames[0].save(
            gif_path,
            save_all=True,
            append_images=optimized[1:],
            duration=200,
            loop=0,
            optimize=True,
            colors=128,
        )
        size_mb = gif_path.stat().st_size / (1024 * 1024)
        log(f"[OK] GIF otimizado: {size_mb:.1f} MB")
    
    return True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        result = asyncio.run(generate_gif())
        sys.exit(0 if result else 1)
    except Exception as e:
        log(f"[ERRO] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)