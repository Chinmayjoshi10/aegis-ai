import pandas as pd
import numpy as np
import datetime

np.random.seed(42)

def generate_data():
    days = 365
    start_date = datetime.date(2023, 1, 1)
    dates = [start_date + datetime.timedelta(days=i) for i in range(days)]
    
    platforms = ["Google Ads", "Facebook Ads", "LinkedIn Ads", "TikTok Ads"]
    
    records = []
    
    # Global Trend Factors
    for day_idx, date in enumerate(dates):
        # Time progression (0 to 1 over the year)
        t = day_idx / days
        
        for plat in platforms:
            # Base daily impressions and spend
            imp = np.random.normal(50000, 5000)
            spend = np.random.normal(500, 50) + (t * 1000)  # Spend increases steadily over the year
            
            bounce_rate = np.random.uniform(0.4, 0.6)
            
            if plat == "Google Ads":
                clicks = imp * np.random.uniform(0.02, 0.04)
                conv_rate = np.random.uniform(0.03, 0.05)
                # Diminishing returns: conv drops off as spend scales up
                if t > 0.5:
                    conv_rate *= (1.0 - (t - 0.5))
                conversions = clicks * conv_rate
                revenue = conversions * np.random.uniform(40, 60)
            
            elif plat == "Facebook Ads":
                # TRAP 1: Facebook Leakage (Tons of cheap clicks, no revenue, high bounce)
                clicks = imp * np.random.uniform(0.08, 0.12) # Huge CTR
                bounce_rate = np.random.uniform(0.85, 0.95)  # Massive Bounce
                conversions = clicks * np.random.uniform(0.001, 0.005) # Terrible CV rate
                revenue = conversions * np.random.uniform(20, 30)
                
            elif plat == "LinkedIn Ads":
                # TRAP 2: LinkedIn Dominance (Low volume, high cost, massive value)
                imp = np.random.normal(10000, 1000) # Lower volume
                spend = np.random.normal(1000, 100) + (t * 800) # High cost
                clicks = imp * np.random.uniform(0.01, 0.02)
                bounce_rate = np.random.uniform(0.1, 0.2) # Exceptional traffic quality
                conversions = clicks * np.random.uniform(0.15, 0.25)
                revenue = conversions * np.random.uniform(300, 500) # Enterprise deals
                
            elif plat == "TikTok Ads":
                # TRAP 3: Extreme Volatility
                volatility_factor = np.random.choice([0.1, 1.0, 3.0])
                clicks = imp * np.random.uniform(0.02, 0.06) * volatility_factor
                conversions = clicks * np.random.uniform(0.01, 0.03)
                revenue = conversions * np.random.uniform(15, 25)
                
            # Compute dependent metrics
            if spend > 0:
                roas = revenue / spend
                tacos = spend / revenue if revenue > 0 else 1.0
            else:
                roas = 0.0
                tacos = 0.0
                
            # Some noise
            spend = max(0, spend + np.random.normal(0, 10))
            conversions = max(0, int(conversions))
            clicks = max(0, int(clicks))
            revenue = max(0, revenue)
                
            records.append({
                "Date": date,
                "Platform": plat,
                "Campaign_Name": f"{plat.replace(' ', '_')}_Q{1 + (day_idx//90)}",
                "Ad_Spend": round(spend, 2),
                "Impressions": int(imp),
                "Clicks": clicks,
                "Conversions": conversions,
                "Revenue": round(revenue, 2),
                "ROAS": round(roas, 2),
                "TACOS": round(tacos, 3),
                "Bounce_Rate": round(bounce_rate, 3)
            })

    df = pd.DataFrame(records)
    # Shuffle a bit within each month but keep chronological macro order
    df.to_csv("Omnichannel_Marketing_Test_Complex.csv", index=False)
    print(f"Generated Omnichannel_Marketing_Test_Complex.csv with {len(df)} rows.")

if __name__ == "__main__":
    generate_data()
