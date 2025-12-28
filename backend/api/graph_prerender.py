"""
Graph position pre-rendering using Playwright
Automates loading a repo on visdep.com to trigger ForceAtlas2 and save positions
"""

import asyncio
import logging
from playwright.async_api import async_playwright


async def prerender_graph_positions(repo_name: str, base_url: str = "https://visdep.com", timeout_minutes: int = 90) -> bool:
    """
    Load a pre-indexed repo in a headless browser to generate and save graph positions.
    
    Args:
        repo_name: e.g., "kubernetes/kubernetes"
        base_url: The visdep URL (production or localhost)
        timeout_minutes: Max time to wait for stabilization
    
    Returns:
        True if successful, False otherwise
    """
    logging.info(f"🖥️ Starting graph pre-render for {repo_name}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        try:
            # 1. Navigate to visdep
            logging.info(f"   Navigating to {base_url}")
            await page.goto(base_url, wait_until='networkidle')
            
            # 2. Find the repo input and enter URL
            repo_url = f"https://github.com/{repo_name}"
            logging.info(f"   Entering repo URL: {repo_url}")
            
            # Wait for input to be ready
            await page.wait_for_selector('input[type="text"]', timeout=30000)
            input_field = await page.query_selector('input[type="text"]')
            await input_field.fill(repo_url)
            
            # 3. Submit by pressing Enter (frontend handles Enter key)
            await page.wait_for_timeout(500)  # Brief wait
            await page.keyboard.press('Enter')
            
            # 4. Wait for graph page to load
            logging.info(f"   Waiting for graph to load...")
            await page.wait_for_timeout(10000)  # Initial wait for pre-indexed detection
            
            # 5. Wait for stabilization
            start_time = asyncio.get_event_loop().time()
            max_time = timeout_minutes * 60
            stable_count = 0
            
            while (asyncio.get_event_loop().time() - start_time) < max_time:
                await page.wait_for_timeout(30000)  # Check every 30 seconds
                
                elapsed = int((asyncio.get_event_loop().time() - start_time) / 60)
                
                # Check stabilization state
                is_stabilized = await page.evaluate('''() => {
                    if (window.network && window.network.physics) {
                        return !window.network.physics.physicsEnabled || window.network.physics.stabilized;
                    }
                    return false;
                }''')
                
                node_count = await page.evaluate('''() => {
                    if (window.network && window.network.body && window.network.body.data) {
                        return window.network.body.data.nodes.length;
                    }
                    return 0;
                }''')
                
                logging.info(f"   [{elapsed}m] Nodes: {node_count}, Stabilized: {is_stabilized}")
                
                if is_stabilized and node_count > 0:
                    stable_count += 1
                    if stable_count >= 3:  # Confirm stable 3 times (90 seconds)
                        logging.info(f"✅ Graph stabilized after {elapsed} minutes")
                        # Wait extra time for async position save to complete
                        logging.info("   Waiting for positions to save to Supabase...")
                        await page.wait_for_timeout(15000)  # 15 seconds for async save
                        return True
                else:
                    stable_count = 0
            
            logging.warning(f"⚠️ Timeout after {timeout_minutes} minutes")
            return False
            
        except Exception as e:
            logging.error(f"❌ Pre-render error: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False
        finally:
            await browser.close()


def run_prerender(repo_name: str, base_url: str = "https://visdep.com") -> bool:
    """Sync wrapper for async prerender function"""
    return asyncio.run(prerender_graph_positions(repo_name, base_url))

