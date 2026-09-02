import os
import asyncio
from tavily import TavilyClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class ConvergenceAnalyzer:
    def __init__(self):
        # 1. Initialize Tavily for Social Context
        self.tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "mock_key_for_build"))
        
        # 2. Initialize the Binance MCP Endpoint
        self.mcp_url = os.getenv("BINANCE_MCP_URL", "https://agent.binance.com/mcp/agentic")
        
        # 3. Setup the NLP Math
        self.historical_narratives = [
            "Retail is aggressively buying this token.",
            "Massive social campaign pushing the token price higher."
        ]
        self.vectorizer = TfidfVectorizer()
        self.historical_vectors = self.vectorizer.fit_transform(self.historical_narratives)

    def fetch_social_data(self, symbol):
        """Uses Tavily API to scrape real-time web chatter about the token."""
        print(f"Scraping social context for {symbol} via Tavily...")
        try:
            # In a real run, this executes: self.tavily_client.search(f"{symbol} crypto sentiment")
            # We mock the return string here for safe execution without an API key
            return f"The community is extremely bullish on {symbol} right now. Massive retail hype."
        except Exception as e:
            return "Neutral market sentiment."

    async def fetch_binance_mcp_data(self, symbol):
        """Connects to the Binance MCP to read live order books."""
        print(f"Connecting to Binance MCP at {self.mcp_url} for {symbol} order book...")
        # Hackathon mock logic representing the MCP Streamable HTTP connection
        # In production, this client pulls the depth via: mcp_client.call_tool("binanceOrderBook", {"symbol": symbol})
        mock_l2_stealth_selling_volume = 850000 
        return mock_l2_stealth_selling_volume

    async def generate_convergence_signal(self, symbol):
        """The actual alpha: Combines social exhaustion (Tavily) with order book data (MCP)."""
        # 1. Get Social Score
        social_text = self.fetch_social_data(symbol)
        current_vector = self.vectorizer.transform([social_text])
        social_score = float(np.max(cosine_similarity(current_vector, self.historical_vectors)))
        
        # 2. Get Market Data
        stealth_volume = await self.fetch_binance_mcp_data(symbol)
        
        # 3. Calculate Convergence
        if social_score > 0.4 and stealth_volume > 500000:
            return {
                "asset": symbol,
                "signal": "HIGH PROBABILITY REVERSAL", 
                "social_exhaustion_score": round(social_score * 100, 2),
                "mcp_sell_wall_detected": True
            }
        return {"asset": symbol, "signal": "NEUTRAL", "social_exhaustion_score": 0}