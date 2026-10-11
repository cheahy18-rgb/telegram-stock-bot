import logging
import yfinance as yf

logger = logging.getLogger(__name__)

def get_stock_info(ticker: str):
    try:
        stock = yf.Ticker(ticker.upper())
        fast_info = stock.fast_info
        price = getattr(fast_info, 'last_price', None)
        if not price:
            return None
            
        info = stock.info
        target_mean = info.get('targetMeanPrice') or (price * 1.2)
        fair_value = target_mean * 0.833
        
        return {
            "ticker": ticker.upper(),
            "name": info.get('longName', ticker.upper()),
            "sector": info.get('sector', 'N/A'),
            "price": price,
            "pe_ratio": info.get('trailingPE', 0),
            "eps": info.get('trailingEps', 0),
            "fair_value": fair_value,
            "target_sell": target_mean
        }
    except Exception as e:
        logger.error(f"Error fetching stock info for {ticker}: {e}")
        return None