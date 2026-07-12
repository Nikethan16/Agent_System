"""prompt_ab.py — A/B test two system-prompt variants for ONE agent.

Runs the same task battery with prompt A and prompt B (the agent's prompt is overridden
per run, then restored), then a strong judge model picks the better answer for each task
PAIRWISE — with the A/B order randomized to cancel position bias. Prints a win tally so you
can keep the prompt that actually performs better, not the one that sounds nicer.

Usage: edit VARIANTS + BATTERY below (or import run_ab), then:
    .venv\\Scripts\\python.exe -m scripts.prompt_ab
"""
import os, sys, json, time, random, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from core import agents as team
from core.agents import agents as registry
from core.llm import complete_chain, Budget
from core.registry import registry as models


def _run_with_prompt(agent_id: str, prompt: str, task: str, max_usd=0.15) -> str:
    a = registry.get(agent_id)
    old = a.prompt
    a.prompt = prompt
    try:
        return team.run(agent_id, task, budget=Budget(max_usd=max_usd, max_iterations=16),
                        use_skills=False)
    except Exception as e:
        return f"(run error: {type(e).__name__}: {e})"
    finally:
        a.prompt = old


_JUDGE_SYS = (
    "You are a strict, impartial evaluator of AI answers. Given a TASK and two answers, decide "
    "which better serves the user — judged on: correctness, directness (leads with the answer), "
    "appropriate conciseness (no filler/preamble), and formatting that fits the question (prose "
    "for simple questions; structure only when it genuinely helps). Output ONLY JSON: "
    '{"winner": 1|2|0, "why": "<=15 words"}  (0 = genuine tie).')


def _judge(task: str, ans1: str, ans2: str) -> int:
    """Returns 1|2 (winner), 0 (genuine tie), or -1 (judge UNAVAILABLE — inconclusive).
    Never silently collapse a rate-limit/parse failure into a 'tie' — retry, then flag it."""
    chain = models.model_chain("tier2", task_type="review")
    prompt = f"TASK:\n{task}\n\n--- ANSWER 1 ---\n{ans1[:2500]}\n\n--- ANSWER 2 ---\n{ans2[:2500]}"
    for attempt in range(3):
        try:
            resp, _ = complete_chain(chain, [{"role": "system", "content": _JUDGE_SYS},
                                             {"role": "user", "content": prompt}],
                                     max_tokens=80, budget=Budget(max_usd=0.05), temperature=0)
            txt = resp.choices[0].message.content or ""
            if "{" in txt and "}" in txt:
                return int(json.loads(txt[txt.find("{"): txt.rfind("}") + 1]).get("winner", 0))
        except Exception:
            pass
        time.sleep(2.5)          # let a rate-limited judge recover before retrying
    return -1                    # could not get a verdict — don't fake a tie


def run_ab(agent_id: str, name_a: str, prompt_a: str, name_b: str, prompt_b: str, battery: list):
    print(f"\n=== A/B on agent '{agent_id}':  A={name_a}  vs  B={name_b} ===")
    wins = {"A": 0, "B": 0, "tie": 0, "err": 0}
    for i, task in enumerate(battery, 1):
        ra = _run_with_prompt(agent_id, prompt_a, task)
        time.sleep(1.5)
        rb = _run_with_prompt(agent_id, prompt_b, task)
        time.sleep(1.5)
        # randomize position so the judge can't be biased by order
        swap = random.random() < 0.5
        w = _judge(task, rb if swap else ra, ra if swap else rb)
        if w == -1:
            winner = "err"                         # judge unavailable — inconclusive
        else:
            winner = "tie" if w == 0 else ("B" if (w == 1) == swap else "A")
        wins[winner] += 1
        print(f"  [{i}] {winner:4}  «{task[:52]}»")
    print(f"--- RESULT:  A({name_a})={wins['A']}   B({name_b})={wins['B']}   "
          f"tie={wins['tie']}   inconclusive={wins['err']} ---")
    better = "A" if wins["A"] > wins["B"] else ("B" if wins["B"] > wins["A"] else "tie")
    print(f"    WINNER: {better}\n")
    return wins


# ---------------------------------------------------------------------------
# DEMO: the 'general' chat agent — current prompt vs a fable-5-informed one
# (default to prose, lead with the answer, honest about uncertainty, no filler).
# ---------------------------------------------------------------------------
_GENERAL_CURRENT = textwrap.dedent("""
    You are a helpful, concise assistant. Answer the user directly in clear
    markdown. You do not have tools — just reply with your best answer. Keep it
    tight and well-structured. (If the user needs files or code produced, that is
    handled by other specialist agents.)""").strip()

_GENERAL_NEW = textwrap.dedent("""
    You are a sharp, helpful assistant. Lead with the direct answer, then only as much
    explanation as the question needs — assume a capable reader; skip preamble and filler.
    Default to natural PROSE; use lists or headings only when they genuinely aid clarity or
    the user asks. Be honest about uncertainty: if you don't know or aren't sure, say so
    plainly rather than guessing, and flag anything that may have changed since your training.
    Don't narrate your process. Match the length of your answer to the question — short for
    simple asks. You have no tools; file/code production is handled by other specialists.""").strip()

_GENERAL_BATTERY = [
    "Explain what a Python decorator is, briefly.",
    "What's the difference between a process and a thread?",
    "Why might an AI system route tasks into difficulty tiers?",
    "Give me 3 tips for writing maintainable code.",
    "What is idempotency and why does it matter in APIs?",
]

if __name__ == "__main__":
    run_ab("general", "current", _GENERAL_CURRENT, "fable5-informed", _GENERAL_NEW,
           _GENERAL_BATTERY)
