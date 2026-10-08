import os
import json
import re
import math
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from backend.engine import run_simulation

app = FastAPI(title="RetireRight AI")
app.mount("/static", StaticFiles(directory="static"), name="static")

GEMINI_API_KEY = "AQ.Ab8RN6LDimElRaS7KW4Waeicm7z_skxgI7d8nnZu_Zej9329IQ"
client = None
try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("\n✅ SUCCESS: Connected to Gemini!\n")
except Exception as e:
    print(f"\n❌ FAILED to initialize Gemini Client: {e}\n")

class PlanRequest(BaseModel):
    current_age: int = 30
    retire_age: int = 60
    current_savings: float = 50000.0
    annual_contribution: float = 15000.0
    annual_spend: float = 30000.0
    baseline_inflation: float = 0.025
    inflation_shock: bool = False
    medical_shock: bool = False
    career_shock: bool = False
    extra_work_years: int = 0
    extra_annual_savings: float = 0.0

class ChatQuery(BaseModel):
    message: str
    current_state: PlanRequest

def calculate_exact_savings(state: dict, target_gap: float = 0.0):
    if state["current_age"] >= state["retire_age"]:
        return state["annual_contribution"]
        
    low = 0.0 
    high = max(state.get("annual_contribution", 0.0), 0.0) + 500000.0
    best_contrib = high
    safe_target = target_gap + 2500.0 
    
    for _ in range(30): 
        mid = (low + high) / 2.0
        test_state = state.copy()
        test_state["annual_contribution"] = mid
        sim_result = run_simulation(**test_state)
        
        if sim_result["gap"] >= safe_target:
            best_contrib = mid
            high = mid
        else:
            low = mid

    return max(0.0, math.ceil(best_contrib / 100.0) * 100.0)

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.post("/api/simulate")
def simulate_plan(payload: PlanRequest):
    return run_simulation(**payload.model_dump())

@app.post("/api/chat")
def handle_chat(query: ChatQuery):
    msg = query.message
    state = query.current_state.model_dump()
    
    reply = ""
    override = {}
    engine_directive = {"action": "NONE", "target_value": 0.0}
    
    if client:
        prompt = f"""
        You are the AI brain of a FinTech operating system. Translate natural language into system updates.
        Current State: {json.dumps(state)}
        User Input: "{msg}"
        
        RULES:
        1. SLIDERS: If they say "age 40" or "savings 50k", map it to "ui_updates".
        2. LOWER TARGET CORPUS: If they say "Lower Target Corpus to 1000000", calculate 1000000 / 25 and set "annual_spend" to that number (which reduces the burden).
        3. SURPLUS/SHORTFALL: If they say "make my surplus 200000" or "fix shortfall", DO NOT update sliders. Set "engine_directive" action to "GOAL_SEEK" and "target_value" to the number (or 0 for shortfall).
        
        Return ONLY valid JSON:
        {{
            "reply": "Conversational response.",
            "ui_updates": {{ "current_age": 40 }},
            "engine_directive": {{ "action": "GOAL_SEEK", "target_value": 200000 }}
        }}
        """
        models_to_test = ['gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-pro']
        for model_name in models_to_test:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw_text = response.text.strip()
                json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if json_match:
                    ai_result = json.loads(json_match.group(0))
                    reply = ai_result.get("reply", "")
                    override = ai_result.get("ui_updates", {})
                    engine_directive = ai_result.get("engine_directive", {"action": "NONE", "target_value": 0.0})
                    break
            except Exception as e:
                continue

    if not reply:
        msg_clean = msg.lower().replace(",", "").replace("$", "")
        if "surplus" in msg_clean:
            match = re.search(r'\d+', msg_clean)
            val = float(match.group()) if match else 0.0
            engine_directive = {"action": "GOAL_SEEK", "target_value": val}
        elif "fix" in msg_clean or "shortfall" in msg_clean:
            engine_directive = {"action": "GOAL_SEEK", "target_value": 0.0}
        else:
            reply = "System online. Ready to accept parameter changes or execute quantitative shortfall recovery."

    if engine_directive.get("action") == "GOAL_SEEK":
        target_gap = float(engine_directive.get("target_value", 0.0))
        current_sim = run_simulation(**state)
        current_gap = current_sim["gap"]
        
        if target_gap == 0.0 and current_gap >= 0:
            reply = "Your mathematical baseline is already secure. No shortfall detected."
        elif target_gap > 0.0 and abs(current_gap - target_gap) < 5000:
            reply = f"Your current surplus already meets your target of ${int(target_gap):,}. No adjustments needed."
        else:
            search_state = state.copy()
            
            if target_gap == 0.0:
                if search_state["current_age"] >= search_state["retire_age"]:
                    new_retire = search_state["current_age"] + 5
                    search_state["retire_age"] = 80 if new_retire > 80 else new_retire
                    override["retire_age"] = search_state["retire_age"]
                else:
                    search_state["retire_age"] = min(search_state["retire_age"] + 3, 80)
                    override["retire_age"] = search_state["retire_age"]
                
            exact_contribution = calculate_exact_savings(search_state, target_gap=target_gap)
            
            if exact_contribution > 120000.0 or exact_contribution >= 490000.0:
                search_state["annual_spend"] = max(10000.0, search_state["annual_spend"] * 0.65)
                override["annual_spend"] = search_state["annual_spend"]
                exact_contribution = calculate_exact_savings(search_state, target_gap=target_gap)
                
            override["annual_contribution"] = exact_contribution
            
            if target_gap == 0.0:
                actions = []
                if "retire_age" in override: actions.append(f"shifted retirement to age {override['retire_age']}")
                if "annual_spend" in override: actions.append(f"slashed Target Spend to ${int(override['annual_spend']):,}")
                actions.append(f"optimized Annual Inflow to ${int(exact_contribution):,}")
                
                actions_text = ", ".join(actions[:-1]) + " and " + actions[-1] if len(actions) > 1 else actions[0]
                reply = f"Quantitative engine executed. To mathematically guarantee a surplus, I have {actions_text}."
            else:
                verb = "reduced" if exact_contribution < state["annual_contribution"] else "optimized"
                reply = f"Quantitative engine executed. To hit exactly a ${int(target_gap):,} surplus, annual savings {verb} to ${int(exact_contribution):,}."

    return {"reply": reply, "state_override": override}
