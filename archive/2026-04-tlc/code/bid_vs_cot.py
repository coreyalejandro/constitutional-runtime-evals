#!/usr/bin/env python3
"""
BID vs CoT Experiment – Full automatic comparison
Run this script to compare two reasoning methods on 5 questions.
"""

import os
import sys
from getpass import getpass
import json

# ---------- STEP 1: Install required library (run this in terminal first) ----------
# Before running this script, open terminal and type:
#   pip install anthropic
# If that fails, try:
#   python -m pip install anthropic

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic library not installed.")
    print("In your terminal, type: pip install anthropic")
    print("Then run this script again.")
    sys.exit(1)

# ---------- STEP 2: Get API key ----------
# You need an Anthropic API key. Get one free at https://console.anthropic.com/
print("\n🔑 Anthropic API Key Required")
print("If you already have it as an environment variable (ANTHROPIC_API_KEY), press Enter.")
print("Otherwise, paste it here (it will NOT be saved, and will be hidden as you type):")
api_key = getpass("> ").strip()
if not api_key:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ No API key found. Set environment variable or paste key.")
        sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)

# ---------- STEP 3: The 5 questions (hardcoded) ----------
questions = [
    "Why is a speeding ticket valid in California?",
    "What caused the French Revolution?",
    "If a train travels 60 mph for 2 hours, how far does it go?",
    "How is a bicycle like a cart?",
    "Explain why the First Amendment protects free speech."
]

# ---------- STEP 4: Prompt templates ----------
# BID prompt – forces backward design
def bid_prompt(question):
    return f"""Answer the following question using **Backward Instructional Design (BID)**.

Step 1 – Identify who needs this answer and what they already know.
Step 2 – Define the final takeaway they must understand.
Step 3 – Build the explanation backwards from that takeaway to simple concepts.

Question: {question}

Answer using BID:"""

# CoT prompt – standard chain of thought
def cot_prompt(question):
    return f"""Answer the following question using **Chain of Thought (CoT)**.

Think step by step, then write your final answer.

Question: {question}

Answer using CoT:"""

# ---------- STEP 5: Simple rubric scoring (keywords based) ----------

# New judge prompt function
def judge_prompt(question, answer):
    return f"""You are an impartial judge evaluating the quality of an AI-generated answer to a question.
Your task is to assess the answer based on three criteria: Clarity, Transferability, and Accuracy.
Provide a score from 1 to 5 for each criterion, where 5 is excellent and 1 is very poor.
Also, provide a brief explanation for each score.

Here is the question:
<question>
{question}
</question>

Here is the AI's answer:
<answer>
{answer}
</answer>

Evaluate the answer using the following criteria and output your assessment in JSON format:

Criteria:
1.  **Clarity**: How easy is the answer to understand? Is it well-structured and free from ambiguity?
2.  **Transferability**: How well does the answer provide insights or principles that could be applied to similar or different contexts? Does it promote deeper understanding beyond the specific question?
3.  **Accuracy**: Is the answer factually correct and relevant to the question?

Output Format (JSON):
```json
{{
  "clarity_score": <score 1-5>,
  "clarity_explanation": "...",
  "transferability_score": <score 1-5>,
  "transferability_explanation": "...",
  "accuracy_score": <score 1-5>,
  "accuracy_explanation": "..."
}}
```
"""
def score_response(text, question):
    if text.startswith("ERROR:"):
        return {"clarity": 1, "transfer": 1, "accuracy": 1}

    try:
        judge_llm_prompt = judge_prompt(question, text)
        judge_resp = client.messages.create(
            model="claude-3-haiku-20240307",
            messages=[{"role": "user", "content": judge_llm_prompt}],
            max_tokens=500,
            temperature=0.0 # Keep temperature low for consistent judging
        )
        judge_output_text = judge_resp.content[0].text
        
        # Extract JSON from the markdown code block
        json_start = judge_output_text.find("```json")
        json_end = judge_output_text.rfind("```")
        if json_start != -1 and json_end != -1:
            json_str = judge_output_text[json_start + len("```json"):json_end].strip()
            scores = json.loads(json_str)
            return {
                "clarity": scores.get("clarity_score", 1),
                "transfer": scores.get("transferability_score", 1),
                "accuracy": scores.get("accuracy_score", 1)
            }
        else:
            print(f"Warning: Could not extract JSON from judge output for question: {question[:50]}...")
            print(f"Judge output: {judge_output_text[:200]}...")
            return {"clarity": 1, "transfer": 1, "accuracy": 1}
    except Exception as e:
        print(f"Error during judge LLM evaluation for question: {question[:50]}... Error: {e}")
        return {"clarity": 1, "transfer": 1, "accuracy": 1}

# ---------- STEP 6: Run the experiment ----------
print("\n🚀 Starting experiment...\n")
results = []

for idx, q in enumerate(questions, 1):
    print(f"📌 Question {idx}/5: {q[:50]}...")
    
    # Get BID answer
    try:
        bid_resp = client.messages.create(
            model="claude-3-haiku-20240307",
            messages=[{"role": "user", "content": bid_prompt(q)}],
            max_tokens=500,
            temperature=0.7
        )
        bid_text = bid_resp.content[0].text
    except Exception as e:
        bid_text = f"ERROR: {e}"
    
    # Get CoT answer
    try:
        cot_resp = client.messages.create(
            model="claude-3-haiku-20240307",
            messages=[{"role": "user", "content": cot_prompt(q)}],
            max_tokens=500,
            temperature=0.7
        )
        cot_text = cot_resp.content[0].text
    except Exception as e:
        cot_text = f"ERROR: {e}"
    
    # Score both
    bid_scores = score_response(bid_text, q)
    cot_scores = score_response(cot_text, q)
    
    results.append({
        "question": q,
        "bid": {"text": bid_text[:200], "scores": bid_scores},
        "cot": {"text": cot_text[:200], "scores": cot_scores}
    })
    
    print(f"   BID clarity={bid_scores['clarity']}, transfer={bid_scores['transfer']}")
    print(f"   CoT clarity={cot_scores['clarity']}, transfer={cot_scores['transfer']}\n")

# ---------- STEP 7: Summary ----------
print("\n" + "="*50)
print("📊 FINAL RESULTS")
print("="*50)

avg_bid_clarity = sum(r["bid"]["scores"]["clarity"] for r in results) / len(results)
avg_cot_clarity = sum(r["cot"]["scores"]["clarity"] for r in results) / len(results)
avg_bid_transfer = sum(r["bid"]["scores"]["transfer"] for r in results) / len(results)
avg_cot_transfer = sum(r["cot"]["scores"]["transfer"] for r in results) / len(results)
avg_bid_accuracy = sum(r["bid"]["scores"]["accuracy"] for r in results) / len(results)
avg_cot_accuracy = sum(r["cot"]["scores"]["accuracy"] for r in results) / len(results)

print(f"Average Clarity    – BID: {avg_bid_clarity:.1f} | CoT: {avg_cot_clarity:.1f}")
print(f"Average Transfer   – BID: {avg_bid_transfer:.1f} | CoT: {avg_cot_transfer:.1f}")
print(f"Average Accuracy   – BID: {avg_bid_accuracy:.1f} | CoT: {avg_cot_accuracy:.1f}")

win_count_clarity = sum(1 for r in results if r["bid"]["scores"]["clarity"] > r["cot"]["scores"]["clarity"])
win_count_transfer = sum(1 for r in results if r["bid"]["scores"]["transfer"] > r["cot"]["scores"]["transfer"])
win_count_accuracy = sum(1 for r in results if r["bid"]["scores"]["accuracy"] > r["cot"]["scores"]["accuracy"])

print(f"\nBID won on clarity for {win_count_clarity}/{len(questions)} questions.")
print(f"BID won on transfer for {win_count_transfer}/{len(questions)} questions.")
print(f"BID won on accuracy for {win_count_accuracy}/{len(questions)} questions.")

print("\n✅ Done. Full details stored in 'results' variable if you run interactively.")
