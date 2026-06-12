#!/usr/bin/env python3
"""
Decision Council CLI - Configuration-driven multi-agent decision making

Usage:
    ./council_cli.py --persona graphics_rendering --decision "Feature selection" --context "constraints.txt"
    ./council_cli.py --persona career_decisions --decision "Job offer comparison" --context offers.json
    ./council_cli.py --list-personas
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.getenv("COUNCIL_BASE_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("COUNCIL_API_KEY") or os.getenv("OLLAMA_API_KEY", "ollama"),
)

LAST_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
LAST_REASONING = {"text": None}

def load_personas():
    """Load all available persona configurations"""
    personas_path = Path(__file__).parent / "personas.json"
    with open(personas_path) as f:
        return json.load(f)

def call_llm(system: str, user: str, temperature: float = 0.4, model: str = "llama3.2:1b",
             model_fallback: str = None, reasoning_effort: str = None) -> str:
    """Call LLM. model_fallback → OpenRouter auto-retries the second model.
    reasoning_effort ('low'|'medium'|'high') → enables reasoning via OpenRouter."""
    extra = {}
    if model_fallback:
        extra["models"] = [model, model_fallback]
    if reasoning_effort:
        extra["reasoning"] = {"effort": reasoning_effort}
    kwargs = {"extra_body": extra} if extra else {}
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        **kwargs,
    )
    usage = getattr(resp, "usage", None)
    if usage:
        pt = getattr(usage, "prompt_tokens", 0)
        ct = getattr(usage, "completion_tokens", 0)
        if isinstance(pt, int) and isinstance(ct, int):
            LAST_USAGE["prompt_tokens"] += pt
            LAST_USAGE["completion_tokens"] += ct
            LAST_USAGE["calls"] += 1
    LAST_REASONING["text"] = getattr(resp.choices[0].message, "reasoning", None)
    return resp.choices[0].message.content

def run_council(idea: str, constraints: str, persona_set: dict) -> dict:
    """Run multi-round debate with given persona set"""
    prompt = f"IDEA:\n{idea}\n\nCONSTRAINTS:\n{constraints}\n"
    debate_transcript = []
    
    # Separate judge from other roles
    roles = {k: v for k, v in persona_set.items() if k != "K_Bot"}
    judge_config = persona_set.get("K_Bot", persona_set[list(persona_set.keys())[0]])
    
    # Round 1: Proposals
    print("\n=== ROUND 1: INITIAL PROPOSALS ===")
    proposals = {}
    for role, config in roles.items():
        print(f"[Round 1] {role} ({config['model']}) proposing...")
        content = call_llm(config['system'], prompt, temperature=0.6, model=config['model'], model_fallback=config.get('model_fallback'), reasoning_effort=config.get('reasoning_effort'))
        proposals[role] = content
        debate_transcript.append({
            "round": 1,
            "role": role,
            "model": config['model'],
            "type": "proposal",
            "content": content,
            "reasoning": LAST_REASONING["text"],
        })
    
    # Round 2: Cross-critiques
    print("\n=== ROUND 2: CROSS-CRITIQUES ===")
    cross_critiques = {}
    for role, config in roles.items():
        other_proposals = {r: p for r, p in proposals.items() if r != role}
        critique_prompt = (
            f"You are critiquing other council members' proposals.\n\n"
            f"Original IDEA: {idea}\n"
            f"CONSTRAINTS: {constraints}\n\n"
            f"OTHER PROPOSALS:\n{json.dumps(other_proposals, indent=2)}\n\n"
            f"Provide specific critiques addressing: assumptions, risks, blind spots, and contradictions."
        )
        print(f"[Round 2] {role} ({config['model']}) critiquing others...")
        content = call_llm(config['system'], critique_prompt, temperature=0.4, model=config['model'], model_fallback=config.get('model_fallback'), reasoning_effort=config.get('reasoning_effort'))
        cross_critiques[role] = content
        debate_transcript.append({
            "round": 2,
            "role": role,
            "model": config['model'],
            "type": "critique",
            "content": content,
            "reasoning": LAST_REASONING["text"],
        })
    
    # Round 3: Rebuttals
    print("\n=== ROUND 3: REBUTTALS & ADJUSTMENTS ===")
    rebuttals = {}
    for role, config in roles.items():
        critiques_of_this_role = {r: c for r, c in cross_critiques.items() if r != role}
        rebuttal_prompt = (
            f"You are responding to critiques of your proposal.\n\n"
            f"Original IDEA: {idea}\n"
            f"CONSTRAINTS: {constraints}\n\n"
            f"YOUR ORIGINAL PROPOSAL:\n{proposals[role]}\n\n"
            f"CRITIQUES FROM OTHER ROLES:\n{json.dumps(critiques_of_this_role, indent=2)}\n\n"
            f"Respond: concede weak points, defend strong points, refine your proposal if needed."
        )
        print(f"[Round 3] {role} ({config['model']}) rebutting critiques...")
        content = call_llm(config['system'], rebuttal_prompt, temperature=0.5, model=config['model'], model_fallback=config.get('model_fallback'), reasoning_effort=config.get('reasoning_effort'))
        rebuttals[role] = content
        debate_transcript.append({
            "round": 3,
            "role": role,
            "model": config['model'],
            "type": "rebuttal",
            "content": content,
            "reasoning": LAST_REASONING["text"],
        })
    
    # Round 4: Judge's decision
    print("\n=== ROUND 4: FINAL JUDGMENT ===")
    judge_prompt = (
        f"Question: {idea}\n\n"
        f"Context: {constraints}\n\n"
        f"PROPOSALS:\n{json.dumps(proposals, indent=2)}\n\n"
        f"CRITIQUES:\n{json.dumps(cross_critiques, indent=2)}\n\n"
        f"REBUTTALS:\n{json.dumps(rebuttals, indent=2)}\n\n"
        f"Make a final decision. Output valid JSON with: decision, rationale, confidence (0-1), next_actions (list)."
    )
    print(f"[Round 4] K_Bot ({judge_config['model']}) making final decision...")
    judge_raw = call_llm(judge_config['system'], judge_prompt, temperature=0.05, model=judge_config['model'], model_fallback=judge_config.get('model_fallback'), reasoning_effort=judge_config.get('reasoning_effort'))
    
    # Parse decision
    try:
        import re
        json_match = re.search(r'```json\n(.*?)\n```', judge_raw, re.DOTALL)
        if json_match:
            decision = json.loads(json_match.group(1))
        else:
            obj_match = re.search(r'\{.*\}', judge_raw, re.DOTALL)
            if obj_match:
                decision = json.loads(obj_match.group())
            else:
                decision = json.loads(judge_raw)
    except Exception as e:
        decision = {"parse_error": True, "raw": judge_raw, "error": str(e)}
    
    debate_transcript.append({
        "round": 4,
        "role": "K_Bot",
        "model": judge_config['model'],
        "type": "decision",
        "content": judge_raw,
        "reasoning": LAST_REASONING["text"],
    })

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "persona_set": {k: v['model'] for k, v in persona_set.items()},
        "idea": idea,
        "constraints": constraints,
        "decision": decision,
        "debate_transcript": debate_transcript,
        "full_debate": {
            "proposals": proposals,
            "cross_critiques": cross_critiques,
            "rebuttals": rebuttals,
            "transcript": debate_transcript,
        },
    }

def print_summary(result: dict):
    """Print concise summary of council decision"""
    print(f"\n{'='*60}")
    print("🎯 DECISION COUNCIL SUMMARY")
    print(f"{'='*60}\n")
    
    print("📋 MODELS USED:")
    for role, model in result['persona_set'].items():
        print(f"  {role:12s}: {model}")
    
    print(f"\n🏆 FINAL DECISION:")
    decision = result['decision']
    
    if isinstance(decision, dict) and not decision.get('parse_error'):
        print(f"   {decision.get('decision', 'N/A')}\n")
        print(f"📊 CONFIDENCE: {decision.get('confidence', 0):.0%}\n")
        print(f"💡 RATIONALE:")
        print(f"   {decision.get('rationale', 'N/A')}\n")
        
        if decision.get('next_actions'):
            print(f"✅ NEXT ACTIONS:")
            for i, action in enumerate(decision['next_actions'][:5], 1):
                print(f"   {i}. {action}")
    else:
        print(f"   ⚠️  Decision parsing failed. Check saved JSON for raw output.")
    
    print(f"\n{'='*60}\n")

def main():
    parser = argparse.ArgumentParser(description="Decision Council CLI")
    parser.add_argument("--persona", "-p", help="Persona set to use (e.g., graphics_rendering, career_decisions)")
    parser.add_argument("--decision", "-d", help="Decision question/idea")
    parser.add_argument("--context", "-c", help="Context/constraints file path")
    parser.add_argument("--list-personas", "-l", action="store_true", help="List all available persona sets")
    parser.add_argument("--output", "-o", help="Output directory (default: runs/)")
    
    args = parser.parse_args()
    
    personas = load_personas()
    
    if args.list_personas:
        print("\n📋 AVAILABLE PERSONA SETS:\n")
        for name, roles in personas.items():
            print(f"  {name}:")
            for role, config in roles.items():
                print(f"    • {role:12s} ({config['model']})")
            print()
        return
    
    if not args.persona or not args.decision:
        parser.print_help()
        print("\n❌ Error: --persona and --decision are required")
        print("   Use --list-personas to see available persona sets")
        sys.exit(1)
    
    if args.persona not in personas:
        print(f"\n❌ Error: Persona set '{args.persona}' not found")
        print(f"   Available: {', '.join(personas.keys())}")
        sys.exit(1)
    
    # Load context if provided
    constraints = ""
    if args.context:
        context_path = Path(args.context)
        if context_path.exists():
            constraints = context_path.read_text()
        else:
            print(f"⚠️  Warning: Context file '{args.context}' not found. Proceeding without context.")
    
    # Run council
    persona_set = personas[args.persona]
    result = run_council(args.decision, constraints, persona_set)
    
    # Save results
    output_dir = Path(args.output) if args.output else Path("runs")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 SAVED: {output_path}")
    
    # Print summary
    print_summary(result)

if __name__ == "__main__":
    main()
