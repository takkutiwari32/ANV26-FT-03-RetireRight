import numpy as np
import yfinance as yf
import concurrent.futures

# Global cache for live market data
MARKET_DATA = {"mean_return": 0.08, "volatility": 0.12, "is_live": False}

def fetch_market_data():
    sp500 = yf.Ticker("^GSPC")
    hist = sp500.history(period="1y")
    daily_returns = hist['Close'].pct_change().dropna()
    live_vol = float(daily_returns.std() * np.sqrt(252))
    live_ret = float(daily_returns.mean() * 252)
    return live_ret, live_vol

try:
    print("Fetching live S&P 500 market data (2-second timeout limit)...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(fetch_market_data)
        # Abort if the hackathon Wi-Fi takes longer than 2 seconds
        live_ret, live_vol = future.result(timeout=2.0) 
        
    MARKET_DATA["mean_return"] = max(0.05, min(live_ret, 0.15))
    MARKET_DATA["volatility"] = max(0.08, min(live_vol, 0.25))
    MARKET_DATA["is_live"] = True
    print("✅ Live market data successfully loaded.")
except concurrent.futures.TimeoutError:
    print("⚠️ yfinance API timeout! Booting instantly with historical fallback.")
except Exception as e:
    print(f"⚠️ Market fetch failed: {e}. Using fallback baseline.")

def run_simulation(
    current_age: int = 30,
    retire_age: int = 60,
    death_age: int = 85,
    current_savings: float = 50000.0,
    annual_contribution: float = 15000.0,
    annual_spend: float = 30000.0,
    baseline_inflation: float = 0.025,
    inflation_shock: bool = False,
    medical_shock: bool = False,
    career_shock: bool = False,
    extra_work_years: int = 0,
    extra_annual_savings: float = 0.0,
    num_simulations: int = 200
):
    effective_retire_age = retire_age + extra_work_years
    total_years = death_age - current_age
    ages = list(range(current_age, death_age + 1))
    
    mean_market_return = MARKET_DATA["mean_return"]
    market_volatility = MARKET_DATA["volatility"]
    
    eff_inflation = baseline_inflation + (0.04 if inflation_shock else 0.0)
    eff_contribution = annual_contribution + extra_annual_savings
    
    trajectories = np.zeros((num_simulations, total_years + 1))
    trajectories[:, 0] = current_savings
    
    np.random.seed(42)
    
    for t in range(total_years):
        age_now = current_age + t
        market_returns = np.random.normal(mean_market_return, market_volatility, num_simulations)
        cost_multiplier = (1.0 + eff_inflation) ** t
        
        is_career_interrupted = career_shock and (40 <= age_now <= 41)
        
        if age_now < effective_retire_age:
            yearly_inflow = 0.0 if is_career_interrupted else eff_contribution
            trajectories[:, t + 1] = trajectories[:, t] * (1.0 + market_returns) + yearly_inflow
        else:
            yearly_outflow = annual_spend * cost_multiplier
            trajectories[:, t + 1] = np.maximum(0.0, trajectories[:, t] * (1.0 + market_returns) - yearly_outflow)
            
        if medical_shock and age_now == 48:
            trajectories[:, t + 1] = np.maximum(0.0, trajectories[:, t + 1] - 45000.0)

    p10 = np.percentile(trajectories, 10, axis=0).tolist()
    p50 = np.percentile(trajectories, 50, axis=0).tolist()
    p90 = np.percentile(trajectories, 90, axis=0).tolist()

    retire_index = min(effective_retire_age - current_age, total_years)
    median_corpus_at_retire = p50[retire_index]
    target_corpus = (annual_spend * ((1.0 + eff_inflation) ** retire_index)) * 25.0
    gap = median_corpus_at_retire - target_corpus
    success_rate = float(np.sum(trajectories[:, -1] > 0) / num_simulations * 100.0)
    
    depletion_age = "N/A"
    for i, val in enumerate(p50):
        if val <= 0.0 and i > 0:
            depletion_age = ages[i]
            break

    recommendations = []
    if gap < 0:
        recommendations.append({"action": "Delay Retirement", "detail": "Delay retirement by 3-5 years."})
        recommendations.append({"action": "Boost Savings", "detail": "Increase annual contributions."})
    else:
        recommendations.append({"action": "Plan Optimized", "detail": f"Surplus achieved (Live Vol: {market_volatility:.1%})."})

    equity_pct = max(20, min(90, 110 - current_age))
    cash_pct = 5
    bonds_pct = 100 - equity_pct - cash_pct
    
    if inflation_shock and bonds_pct > 10:
        bonds_pct -= 10
        equity_pct += 10

    allocation = {
        "labels": ["Equities (S&P 500)", "Fixed Income (Bonds)", "Cash/Reserves"],
        "data": [equity_pct, bonds_pct, cash_pct]
    }

    return {
        "ages": ages,
        "p10_pessimistic": [round(val, 2) for val in p10],
        "p50_median": [round(val, 2) for val in p50],
        "p90_optimistic": [round(val, 2) for val in p90],
        "target_corpus": round(target_corpus, 2),
        "gap": round(gap, 2),
        "status": "Surplus" if gap >= 0 else "Shortfall",
        "success_rate": round(success_rate, 1),
        "depletion_age": depletion_age,
        "recommendations": recommendations,
        "allocation": allocation
    }