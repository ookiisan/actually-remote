"""
Pluggable AI provider abstraction.
Supports: Google Gemini (default), Anthropic Claude, OpenAI, Ollama.
Handles location pre-filtering and CV match scoring.
"""
import json


def mock_analyze_job_fit(job_title, job_description, cv_text):
    """Fake Gemini response for testing purposes"""
    print(f"    [MOCK AI] Analyzing: {job_title}")
    return {
        "fit_score": 8,
        "reasons_for": ["Matches title keywords", "Remote EMEA friendly"],
        "reasons_against": ["None"],
        "recommendation": "Apply",
        "summary": "This is a mock response to save tokens."
    }


def analyze_job_fit(model, job_title, job_description, cv_text):
    """Use Gemini to analyze job fit"""
    prompt = f"""You are a job application assistant helping evaluate job fit.
Compare this job description against the CV and return a concise assessment.

CV:
{cv_text}

Job Title: {job_title}

Job Description:
{job_description}

Return JSON only, no explanation outside the JSON:
{{
  "fit_score": 8,
  "reasons_for": [
    "3+ years Python experience matches requirement",
    "Target company — strong cultural fit"
  ],
  "reasons_against": [
    "PostgreSQL internals may need brushing up"
  ],
  "recommendation": "Apply",
  "summary": "Strong match on technical and customer-facing experience."
}}

Rules:
- Use "you/your" not "the candidate" or "her/his"
- reasons_for: max 3 items, focus on tech stack and role requirements
- reasons_against: max 2 items, be specific about the gap
- Keep each point under 15 words
- fit_score: 1-10 based on requirements match only"""

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        return json.loads(response_text)
    except Exception as e:
        print(f"    ⚠️ AI analysis failed: {str(e)}")
        return None
