"""
Quick test for Diario Oficial scraper
- Tests only 1 date (yesterday)
- 60 second total timeout
- Debug mode by default (visible browser)
- Detailed logs at each step
"""
import asyncio
import os
import argparse
from datetime import datetime, timedelta
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from scraper_service import DiarioScraper

async def quick_test(headless=False):
    debug_mode = not headless
    scraper = DiarioScraper(debug=debug_mode)
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    
    print("=" * 70)
    print("🚀 TESTE RÁPIDO DO SCRAPER")
    print("=" * 70)
    print(f"📅 Data: {yesterday}")
    print(f"🔧 Modo: {'HEADLESS (invisível)' if headless else 'DEBUG (visível)'}")
    print(f"⏱️  Timeout: 60 segundos")
    print("=" * 70)
    print()
    
    async def log(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            print(f"[{timestamp}] {msg}")
        except UnicodeEncodeError:
            print(f"[{timestamp}] {msg.encode('ascii', 'ignore').decode('ascii')}")
    
    try:
        start_time = datetime.now()
        
        # Total timeout of 60 seconds
        results = await asyncio.wait_for(
            scraper.scrape(yesterday, yesterday, [], status_callback=log),
            timeout=60
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print()
        print("=" * 70)
        print(f"✅ SUCESSO!")
        print(f"⏱️  Tempo total: {elapsed:.1f} segundos")
        print(f"📊 Resultados: {len(results)}")
        print("=" * 70)
        
        if results:
            print("\n📄 Amostra dos resultados:")
            for i, r in enumerate(results[:3], 1):
                print(f"\n{i}. Termo: {r.term}")
                print(f"   Processo: {r.process_number}")
                print(f"   Documento: {r.document_id}")
                print(f"   Resumo: {r.summary[:80]}...")
        else:
            print("\n⚠️  Nenhuma publicação encontrada")
            print("💡 Isso pode ser normal se não houver publicações relevantes")
        
        return True
        
    except asyncio.TimeoutError:
        elapsed = (datetime.now() - start_time).total_seconds()
        print()
        print("=" * 70)
        print(f"❌ TIMEOUT após {elapsed:.1f} segundos")
        print("=" * 70)
        print("\n💡 Possíveis causas:")
        print("   1. Site do Diário Oficial está lento/fora do ar")
        print("   2. Conexão de internet instável")
        print("   3. Anti-bot bloqueando acesso automatizado")
        print("\n🔧 Tente:")
        print("   - Rodar novamente após alguns minutos")
        print("   - Verificar se o site está acessível no navegador normal")
        print("   - Usar modo debug para ver onde trava: python quick_test.py")
        return False
        
    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ ERRO: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Teste rápido do scraper')
    parser.add_argument('--headless', action='store_true', 
                       help='Executar em modo headless (padrão é debug/visível)')
    args = parser.parse_args()
    
    success = asyncio.run(quick_test(headless=args.headless))
    sys.exit(0 if success else 1)
